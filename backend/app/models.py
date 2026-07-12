from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class ExerciseTemplate(SQLModel, table=True):
    """Cached from GET /v1/exercise_templates. Maps exercise name <-> UUID and holds
    muscle-group info used for volume-per-muscle analysis."""

    id: str = Field(primary_key=True)  # UUID from Hevy
    title: str = Field(index=True)
    type: Optional[str] = None
    primary_muscle_group: Optional[str] = None
    secondary_muscle_groups: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    is_custom: bool = False


class Workout(SQLModel, table=True):
    """One logged workout session (GET /v1/workouts)."""

    id: str = Field(primary_key=True)  # Hevy workout id
    title: Optional[str] = None
    description: Optional[str] = None  # workout-level notes
    routine_id: Optional[str] = None
    start_time: Optional[datetime] = Field(default=None, index=True)
    end_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WorkoutSet(SQLModel, table=True):
    """A single set, flattened with denormalized exercise info for fast trend queries.
    Exercise notes (e.g. 'felt sloppy', 'burnt out from AMRAP') live here and are used
    heavily by the coach."""

    id: Optional[int] = Field(default=None, primary_key=True)
    workout_id: str = Field(foreign_key="workout.id", index=True)
    workout_start_time: Optional[datetime] = Field(default=None, index=True)

    exercise_index: int = 0
    exercise_title: str = Field(index=True)
    exercise_template_id: Optional[str] = Field(default=None, index=True)
    exercise_notes: Optional[str] = None

    set_index: int = 0
    set_type: Optional[str] = None  # normal | warmup | dropset | failure
    weight_kg: Optional[float] = None
    reps: Optional[int] = None
    distance_meters: Optional[float] = None
    duration_seconds: Optional[float] = None
    rpe: Optional[float] = None


class BodyMeasurement(SQLModel, table=True):
    """Bodyweight + body-fat % from Hevy's body_measurements (fed by Apple Health / a smart
    scale). Only weight and fat% come through Hevy's API."""

    id: int = Field(primary_key=True)  # Hevy measurement id
    date: str = Field(index=True)  # YYYY-MM-DD
    weight_kg: Optional[float] = None
    fat_percent: Optional[float] = None
    created_at: Optional[str] = None


class SyncState(SQLModel, table=True):
    """Single-row (id=1) record of sync progress."""

    id: int = Field(default=1, primary_key=True)
    full_sync_done: bool = False
    last_synced_at: Optional[datetime] = None
    workout_count: int = 0
    templates_synced_at: Optional[datetime] = None


class RoutineProposal(SQLModel, table=True):
    """A routine Claude proposed (in chat or in the weekly review). Never pushed to Hevy
    until approval triggers the push. `payload` is Claude's structured proposal;
    `resolved_payload` is the exact body sent to Hevy (names->UUIDs, wrapped, sanitized).

    kind='create' -> POST a new routine; kind='update' -> PUT (full overwrite) the routine
    at `target_routine_id`. `diff` holds a human-readable rationale/summary for the card."""

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending", index=True)  # pending|pushed|failed
    title: str = ""
    kind: str = Field(default="create")  # create | update
    target_routine_id: Optional[str] = None  # for kind=update
    source: str = Field(default="chat")  # chat | weekly
    # The assistant ChatMessage this proposal was created in, so its approval card can be
    # replayed from chat history after a reload (streamed proposal events are ephemeral).
    chat_message_id: Optional[int] = Field(default=None, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    diff: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    resolved_payload: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    hevy_routine_id: Optional[str] = None
    error: Optional[str] = None


class ChatMessage(SQLModel, table=True):
    """Persisted chat turns (text only) so the coach has memory across sessions."""

    id: Optional[int] = Field(default=None, primary_key=True)
    role: str  # user | assistant
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class AppState(SQLModel, table=True):
    """Tiny key/value memory store: cached generated content (e.g. the dashboard summary,
    so it isn't regenerated on every page load) and user preferences (e.g. weight unit)."""

    key: str = Field(primary_key=True)
    value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WeeklyReview(SQLModel, table=True):
    """A generated weekly review. `payload` holds the narrative + computed signals +
    the ids of the RoutineProposal rows it produced."""

    id: Optional[int] = Field(default=None, primary_key=True)
    generated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    period_start: datetime
    period_end: datetime
    status: str = Field(default="ready")
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
