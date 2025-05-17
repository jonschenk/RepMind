from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from backend.utils import parse_hevy_csv, chunk_workout_data
from backend.embeddings import embed_texts
from backend.vectorstore import add_workout_chunks

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
    contents = await file.read()
    workouts = parse_hevy_csv(contents)
    chunks = chunk_workout_data(workouts)
    embeddings = embed_texts(chunks)
    add_workout_chunks(chunks, embeddings)
    return {"message": f"Processed {len(chunks)} chunks"}

@app.post("/ask")
async def ask_question(data: dict):
    question = data.get("question", "")
    # TODO: embed question, retrieve context, run LLM
    return {"answer": "This is a placeholder answer"}