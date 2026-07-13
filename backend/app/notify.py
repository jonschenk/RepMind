"""Push notifications via ntfy (https://ntfy.sh).

Publish is a plain HTTP POST to {server}/{topic}; the user's phone receives it through the
ntfy app subscribed to that topic. Best-effort: a failed or unconfigured notification never
breaks the caller. Kept deliberately low-content (a count, not the training data itself) so
nothing sensitive transits the public ntfy relay."""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("repmind.notify")


async def send_notification(
    title: str,
    message: str,
    *,
    tags: list[str] | None = None,
    priority: int | None = None,
    click: str | None = None,
) -> bool:
    """POST a notification to the configured ntfy topic. Returns True if sent. `title` and
    header values must be ASCII (ntfy headers are latin-1); use `tags` for emoji."""
    settings = get_settings()
    if not settings.ntfy_configured:
        return False
    url = f"{settings.ntfy_server.rstrip('/')}/{settings.ntfy_topic}"
    headers: dict[str, str] = {"Title": title}
    if tags:
        headers["Tags"] = ",".join(tags)
    if priority is not None:
        headers["Priority"] = str(priority)
    if click:
        headers["Click"] = click
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=message.encode("utf-8"), headers=headers)
        if resp.status_code >= 400:
            logger.warning("ntfy POST failed (%s): %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("ntfy notification failed: %s", exc)
        return False
