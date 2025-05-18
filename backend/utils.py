import csv
from typing import List, Dict, Tuple

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


def chunk_workout_data(workouts: List[Dict], chunk_size: int = 5) -> Tuple[List[str], List[dict]]:
    """
    Break a list of workout dicts into chunks of concatenated strings with date info.
    
    Args:
        workouts: List of workout entries parsed from CSV.
        chunk_size: Number of workout entries per chunk.
        
    Returns:
        A tuple of:
            - List of string chunks with embedded workout info
            - List of metadata dicts, one per chunk
    """
    chunks = []
    metadatas = []

    for i in range(0, len(workouts), chunk_size):
        chunk_items = workouts[i:i + chunk_size]
        chunk_text_lines = []

        # Use the earliest date in this chunk as metadata (fallback to unknown)
        dates_in_chunk = [item.get('start_time', 'unknown') for item in chunk_items]
        chunk_date = min(dates_in_chunk) if dates_in_chunk else 'unknown'

        for item in chunk_items:
            chunk_text_lines.append(
                f"Date: {item['start_time']}, Exercise: {item['exercise_title']}, "
                f"Set: {item['set_index']}, Reps: {item['reps']}, "
                f"Weight: {item['weight_lbs']} lbs, RPE: {item['rpe']}"
            )

        chunk_text = "\n".join(chunk_text_lines)
        chunks.append(chunk_text)

        metadatas.append({
            "date": chunk_date
        })

    return chunks, metadatas
