from langchain_ollama import OllamaLLM
from backend.chains.sqlitechain import get_sqlite_chain
from backend.chains.vectorchain import get_vector_chain
import re
import ast

llm = OllamaLLM(model="deepseek-llm")

ROUTER_PROMPT = """
You are a routing agent. Given a question, decide if it's a stats/trend question (route to "stats_db") or a comparison/similarity question (route to "vector_db").
if someone asks you how many times you did something, assign it the vector_db.

Question: {input}

Return only the routing keyword: "stats_db" or "vector_db".
"""

def route_question(question: str) -> str:
    prompt = ROUTER_PROMPT.format(input=question)
    response = llm.invoke(prompt)
    keyword = response.strip().lower()
    if "stats_db" in keyword:
        return "stats_db"
    elif "vector_db" in keyword:
        return "vector_db"
    else:
        return "vector_db"  # Default fallback

def format_sql_result(question, sql_result):
    if not sql_result or len(sql_result) == 0:
        return "No result found for your query."
    # If the result is a list of tuples with multiple columns
    if isinstance(sql_result[0], (list, tuple)):
        # If your DB returns column names, you can map them, or just print as key-value pairs
        columns = [
            "id", "title", "start_time", "end_time", "description", "exercise_title", "superset_id",
            "exercise_notes", "set_index", "set_type", "weight_lbs", "reps", "distance_miles",
            "duration_seconds", "rpe"
        ]
        event = dict(zip(columns, sql_result[0]))
        return "Event details:\n" + "\n".join(f"{k}: {v}" for k, v in event.items())
    elif isinstance(sql_result[0], dict):
        event = sql_result[0]
        return "Event details:\n" + "\n".join(f"{k}: {v}" for k, v in event.items())
    else:
        return "Results: " + ", ".join(str(x) for x in sql_result)

def extract_sql_result(response):
    """
    Tries to extract the SQL result from the chain response, handling various formats.
    """
    # Try intermediate_steps for a string that looks like a SQL result
    if "intermediate_steps" in response:
        steps = response["intermediate_steps"]
        for step in steps:
            if isinstance(step, str) and step.strip().startswith("["):
                try:
                    return ast.literal_eval(step)
                except Exception:
                    continue
    # Fallback: try 'result' key if it's a list
    if "result" in response and isinstance(response["result"], list):
        return response["result"]
    # Fallback: try 'result' key if it's a string that looks like a list
    if "result" in response and isinstance(response["result"], str):
        try:
            return ast.literal_eval(response["result"])
        except Exception:
            pass
    return None

def ask_llm(question: str):
    route = route_question(question)
    if route == "stats_db":
        chain = get_sqlite_chain(llm)
        response = chain.invoke(question)
        print("DEBUG: Full response:", response)

        sql_result = extract_sql_result(response)
        print("DEBUG: Extracted SQL result:", sql_result)

        return format_sql_result(question, sql_result)
    else:
        chain = get_vector_chain(llm)
        response = chain.invoke(question)
        return response["result"]