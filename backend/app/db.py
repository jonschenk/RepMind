from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()

# check_same_thread=False so FastAPI's threadpool can share the SQLite connection.
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


# New columns added to existing tables after the first release. SQLite create_all won't
# ALTER an existing table, so we add any missing columns idempotently on startup. The DB is
# a rebuildable cache, so this stays lightweight rather than a full migration framework.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "routineproposal": {
        "kind": "TEXT DEFAULT 'create'",
        "target_routine_id": "TEXT",
        "source": "TEXT DEFAULT 'chat'",
        "diff": "JSON",
        "chat_message_id": "INTEGER",
        "pushed_at": "DATETIME",
    },
}


def _add_missing_columns() -> None:
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).all()
            }
            if not existing:  # table doesn't exist yet; create_all will make it fresh
                continue
            for name, decl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {decl}"))


def init_db() -> None:
    # Import models so their tables register on SQLModel.metadata before create_all.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
