from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from backend.utils import parse_hevy_csv, chunk_workout_data
from backend.embeddings import embedding_model
from backend.vectorstore import add_workout_chunks, get_collection
from backend.langchain_chain import ask_with_langchain

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
        chunks, metadatas = chunk_workout_data(workouts)
        add_workout_chunks(chunks, metadatas)
        return {"message": f"Processed {len(chunks)} chunks"}
    except Exception as e:
        return {"error": f"Failed to process CSV: {str(e)}"}


@app.post("/ask")
async def ask_question(data: dict):
    question = data.get("question", "")
    if not question:
        return {"error": "Question field is required"}

    try:
        answer = ask_with_langchain(question)
        return {
            "question": question,
            "answer": answer
        }
    except Exception as e:
        return {"error": f"LangChain error: {str(e)}"}


@app.get("/debug-docs")
def debug_docs():
    collection = get_collection()
    results = collection.get()
    return {"ids": results.get("ids"), "documents": results.get("documents")}