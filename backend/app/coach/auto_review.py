"""Trigger the weekly review when the user finishes their training week, instead of only on
a fixed schedule.

"Finished the week" = since the last review, every routine in the active split (the Hevy
folder they've been training most recently) has been logged. When the last remaining day is
completed, the next sync sees full coverage and fires the review. Two rails keep it sane:
a FLOOR (never fire twice within a few days) and a CEILING (if too long passes without a
clean completion, fire on the next workout so it never stalls). The Monday cron stays as a
backup that skips itself when a workout-triggered review already ran."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.coach.weekly_review import generate_weekly_review
from app.config import get_settings
from app.hevy import HevyClient
from app.models import WeeklyReview, Workout
from app.notify import send_notification
from app.state import get_state, set_state

logger = logging.getLogger("repmind.autoreview")

FLOOR_DAYS = 4  # don't fire another review within this window
CEILING_DAYS = 9  # if this long passes without a clean cycle, fire on the next workout

# The rotation anchor: the point we measure split coverage from. It is advanced ONLY by a
# genuine completion (cycle-complete or ceiling), never by a cron/manual review. That way a
# review landing mid-rotation (e.g. the Monday cron, since a 6-day split doesn't align to a
# 7-day week) doesn't orphan the rotation's early days from the completion count.
CYCLE_ANCHOR_KEY = "cycle_anchor"


def _latest_review(session: Session) -> WeeklyReview | None:
    return session.exec(
        select(WeeklyReview).order_by(WeeklyReview.generated_at.desc())
    ).first()


async def _fire(session: Session, client: HevyClient, reason: str) -> dict:
    review = await generate_weekly_review(session, client)
    n = len(review.get("proposals", []))
    settings = get_settings()
    await send_notification(
        "repMind weekly review ready",
        f"Your weekly training review is ready ({n} proposed change{'' if n == 1 else 's'}). "
        "Open the Weekly tab to review.",
        tags=["chart_with_upwards_trend"],
        click=settings.app_url,
    )
    logger.info("Weekly review generated (trigger: %s).", reason)
    return review


def _folder_coverage(
    routines: list[dict], workouts_since: list[Workout]
) -> tuple[set | None, dict]:
    """For the ACTIVE split (the folder of the most recent workout), return its routine-id set
    and, for each of those routines logged since `since`, the FIRST time it appeared. Returns
    (None, {}) if the active split can't be determined (e.g. a freestyle workout with no
    routine)."""
    most_recent = max(workouts_since, key=lambda w: w.start_time)
    rmap = {r.get("id"): r for r in routines}
    active = rmap.get(most_recent.routine_id)
    if not active or active.get("folder_id") is None:
        return None, {}
    folder_id = active["folder_id"]
    folder_routine_ids = {r.get("id") for r in routines if r.get("folder_id") == folder_id}
    first_seen: dict = {}
    for w in sorted(
        (w for w in workouts_since if w.routine_id in folder_routine_ids),
        key=lambda w: w.start_time,
    ):
        first_seen.setdefault(w.routine_id, w.start_time)
    return folder_routine_ids, first_seen


def cycle_reason(
    session: Session, routines: list[dict], since: datetime, now: datetime
) -> str | None:
    """Pure decision (no side effects): should the review fire, and why?
    Returns 'ceiling', 'cycle-complete', or None. `since` is the rotation anchor (the last
    completion, or a week ago for the first ever). `routines` is the live Hevy routine list."""
    workouts_since = [
        w for w in session.exec(select(Workout)).all() if w.start_time and w.start_time > since
    ]
    if not workouts_since:
        return None

    # Stall guard: too long without a clean completion -> fire on this workout.
    if (now - since) > timedelta(days=CEILING_DAYS):
        return "ceiling"

    # Split-coverage: has every routine in the active folder been logged since `since`?
    folder_routine_ids, first_seen = _folder_coverage(routines, workouts_since)
    if folder_routine_ids and folder_routine_ids <= set(first_seen):
        return "cycle-complete"
    return None


def _completion_anchor(
    session: Session, routines: list[dict], since: datetime, now: datetime, reason: str
) -> datetime:
    """Where to move the rotation anchor after a fire. For 'ceiling' we reset to now. For
    'cycle-complete' we move it to the moment the rotation completed (the last split routine's
    first appearance), NOT the latest workout, so any next-rotation days already logged (e.g.
    when a FLOOR delay pushes the fire past the completion) stay counted for the next cycle."""
    if reason != "cycle-complete":
        return now
    workouts_since = [
        w for w in session.exec(select(Workout)).all() if w.start_time and w.start_time > since
    ]
    _, first_seen = _folder_coverage(routines, workouts_since)
    return max(first_seen.values()) if first_seen else now


def _get_anchor(session: Session, last_review: WeeklyReview | None, now: datetime) -> datetime:
    """The rotation anchor to measure coverage from. Falls back to the last review time (or a
    week ago) until a real completion has stored one."""
    raw = get_state(session, CYCLE_ANCHOR_KEY)
    if raw and raw.get("at"):
        try:
            return datetime.fromisoformat(raw["at"])
        except (ValueError, TypeError):
            pass
    return last_review.generated_at if last_review else now - timedelta(days=7)


def _set_anchor(session: Session, when: datetime) -> None:
    set_state(session, CYCLE_ANCHOR_KEY, {"at": when.isoformat()})


async def maybe_generate_on_cycle(session: Session, client: HevyClient) -> bool:
    """Fire the review if the active split has been fully covered since the rotation anchor.
    Cheap until eligible: the get_routines call only happens past the FLOOR window."""
    settings = get_settings()
    if not (settings.hevy_configured and settings.anthropic_configured):
        return False

    now = datetime.utcnow()
    last = _latest_review(session)
    if last and (now - last.generated_at) < timedelta(days=FLOOR_DAYS):
        return False  # too soon since the last review (avoid double content)

    # Coverage is measured from the rotation anchor, not the last review: a cron/manual review
    # that landed mid-rotation must not orphan the rotation's earlier days.
    anchor = _get_anchor(session, last, now)
    if not any(w.start_time and w.start_time > anchor for w in session.exec(select(Workout)).all()):
        return False  # no new workouts -> skip the Hevy call entirely

    try:
        routines = await client.get_routines()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cycle check: get_routines failed: %s", exc)
        return False

    reason = cycle_reason(session, routines, anchor, now)
    if reason:
        await _fire(session, client, reason)
        # Advance the anchor to the completion point so the next rotation is measured cleanly.
        _set_anchor(session, _completion_anchor(session, routines, anchor, now, reason))
        return True
    return False


async def cron_backup(session: Session, client: HevyClient) -> bool:
    """Scheduled Monday job: generate unless a review already ran within the FLOOR window."""
    now = datetime.utcnow()
    last = _latest_review(session)
    if last and (now - last.generated_at) < timedelta(days=FLOOR_DAYS):
        logger.info("Weekly cron skipped; a review ran %s ago.", now - last.generated_at)
        return False
    await _fire(session, client, "cron-backup")
    return True
