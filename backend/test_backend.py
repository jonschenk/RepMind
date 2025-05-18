import pytest
from fastapi.testclient import TestClient
from backend.sqlitestore import query_workouts
from backend.main import app

client = TestClient(app)

def test_query_existing_workouts():
    # Query all workouts from your existing DB
    workouts = query_workouts("SELECT * FROM workout_sets")

    # Basic sanity checks (adjust to your actual data)
    assert len(workouts) > 0, "No workouts found in the database"
    print(f"{len(workouts)} sets found")
    assert any("bench press" in w["exercise_title"].lower() for w in workouts), "Bench Press not found"