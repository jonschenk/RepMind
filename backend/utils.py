import csv
from typing import List, Dict

def parse_hevy_csv(contents: bytes) -> List[Dict]:
    decoded = contents.decode('utf-8').splitlines()
    reader = csv.DictReader(decoded)
    workouts = []
    for row in reader:
        workouts.append({
            "title": row.get("title"),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "description": row.get("description"),
            "exercise_title": row.get("exercise_title"),
            "superset_id": row.get("superset_id"),
            "exercise_notes": row.get("exercise_notes"),
            "set_index": int(row.get("set_index", 0)),
            "set_type": row.get("set_type"),
            "weight_lbs": float(row.get("weight_lbs", 0) or 0),
            "reps": int(row.get("reps", 0) or 0),
            "distance_miles": float(row.get("distance_miles", 0) or 0),
            "duration_seconds": int(row.get("duration_seconds", 0) or 0),
            "rpe": float(row.get("rpe", 0) or 0),
        })
    return workouts


def chunk_workout_data(workouts: List[Dict], chunk_size: int = 5) -> List[str]:
    """
    Break a list of workout dicts into chunks of concatenated strings.
    
    Args:
        workouts: List of workout entries parsed from CSV.
        chunk_size: Number of workout entries per chunk.
        
    Returns:
        List of string chunks, each containing multiple workouts concatenated.
    """
    chunks = []
    for i in range(0, len(workouts), chunk_size):
        chunk_items = workouts[i:i + chunk_size]
        chunk_text = "\n".join(
            f"Exercise: {item['exercise_title']}, Sets: {item['set_index']}, "
            f"Reps: {item['reps']}, Weight: {item['weight_lbs']} lbs, RPE: {item['rpe']}"
            for item in chunk_items
        )
        chunks.append(chunk_text)
    return chunks