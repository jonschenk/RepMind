import sqlite3

SQLITE_DB_PATH = "./workout_stats.db"

def insert_workouts_into_sqlite(workouts: list[dict]):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM workout_sets")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workout_sets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        start_time TEXT,
        end_time TEXT,
        description TEXT,
        exercise_title TEXT,
        superset_id TEXT,
        exercise_notes TEXT,
        set_index INTEGER,
        set_type TEXT,
        weight_lbs REAL,
        reps INTEGER,
        distance_miles REAL,
        duration_seconds INTEGER,
        rpe REAL
    );
    """)

    for w in workouts:
        cursor.execute("""
            INSERT INTO workout_sets (
                title, start_time, end_time, description,
                exercise_title, superset_id, exercise_notes,
                set_index, set_type, weight_lbs, reps,
                distance_miles, duration_seconds, rpe
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            w.get("title"),
            w.get("start_time"),
            w.get("end_time"),
            w.get("description"),
            w.get("exercise_title"),
            w.get("superset_id"),
            w.get("exercise_notes"),
            w.get("set_index"),
            w.get("set_type"),
            w.get("weight_lbs"),
            w.get("reps"),
            w.get("distance_miles"),
            w.get("duration_seconds"),
            w.get("rpe")
        ))

    conn.commit()
    conn.close()


def query_workouts(query):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]