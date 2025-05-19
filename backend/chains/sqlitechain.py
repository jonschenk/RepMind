from langchain.prompts import FewShotPromptTemplate, PromptTemplate
from langchain_experimental.sql import SQLDatabaseChain
from langchain_community.utilities.sql_database import SQLDatabase

def get_sqlite_chain(llm):
    db = SQLDatabase.from_uri("sqlite:///workout_stats.db")
    examples = [
        {
            "question": "What was my heaviest squat?",
            "sql": "SELECT * FROM workout_sets WHERE exercise_title LIKE '%Squat%' ORDER BY weight_lbs DESC LIMIT 1;"
        },
        {
            "question": "What was my second heaviest bench?",
            "sql": "SELECT * FROM workout_sets WHERE exercise_title LIKE '%Bench%' ORDER BY weight_lbs DESC LIMIT 1 OFFSET 1;"
        },
        {
            "question": "How many times did I do deadlifts?",
            "sql": "SELECT COUNT(*) FROM workout_sets WHERE exercise_title LIKE '%Deadlift%';"
        },
        {
            "question": "What is the average weight for bench press sets?",
            "sql": "SELECT AVG(weight_lbs) FROM workout_sets WHERE exercise_title LIKE '%Bench%';"
        },
        {
            "question": "How many times did I bench in April 2025?",
            "sql": "SELECT COUNT(*) FROM workout_sets WHERE exercise_title LIKE '%Bench%' AND strftime('%Y', start_time) = '2025' AND strftime('%m', start_time) = '04';"
        }
    ]

    example_prompt = PromptTemplate(
        input_variables=["question", "sql"],
        template="Question: {question}\nSQL: {sql}"
    )

    sql_prompt = FewShotPromptTemplate(
        examples=examples,
        example_prompt=example_prompt,
        prefix=(
            "You are an expert fitness data analyst. "
            "Given a user's natural language question about their workouts and the database schema, "
            "generate a correct, concise SQL query that answers the question. "
            "Return ONLY the SQL query. Do NOT include any explanation, comments, or text. "
            "Do NOT start your answer with anything except the SQL SELECT statement. "
            "If you are unsure, output a valid SQL query that returns no rows, like: SELECT * FROM workout_sets WHERE 1=0;"
            "\n\n"
            "Here are some examples:\n"
        ),
        suffix=(
            "\nNow, answer the following:\n"
            "Question: {input}\n"
            "Schema: {table_info}\n"
            "SQL:"
        ),
        input_variables=["input", "table_info"]
    )

    return SQLDatabaseChain.from_llm(
        llm=llm,
        db=db,
        prompt=sql_prompt,
        return_intermediate_steps=True  # For debugging!
    )
