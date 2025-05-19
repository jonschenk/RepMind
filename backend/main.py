from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.utils import parse_hevy_csv, chunk_workout_data
from backend.embeddings import embedding_model
from backend.vectorstore import add_workout_chunks, get_collection
from backend.sqlitestore import insert_workouts_into_sqlite
from backend.router_agent import ask_llm

app = FastAPI()

# Allow frontend requests


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # TODO Later, set frontend URL here
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "RepMind backend is live"}


@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        workouts = parse_hevy_csv(contents)

        # add to vectorstore
        chunks, metadatas = chunk_workout_data(workouts)
        add_workout_chunks(chunks, metadatas)

        insert_workouts_into_sqlite(workouts)

        return {"message": f"Processed {len(chunks)} chunks"}
    

    except Exception as e:
        return {"error": f"Failed to process CSV: {str(e)}"}


@app.post("/ask")
async def ask_question(request: Request):
    data = await request.json()
    question = data.get("question", "").strip()
    
    if not question:
        return {"error": "Question field is required"}

    try:
        # Run question through the RouterChain
        response = ask_llm(question)
        return {"question": question, "answer": response}
    except Exception as e:
        return {"error": f"RouterChain processing error: {str(e)}"}


@app.get("/debug-docs")
def debug_docs():
    collection = get_collection()
    results = collection.get()
    return {"ids": results.get("ids"), "documents": results.get("documents")}