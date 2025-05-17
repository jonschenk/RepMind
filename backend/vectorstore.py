import chromadb
from chromadb.config import Settings
from backend.embeddings import embed_texts


settings = Settings(
    persist_directory="./chroma_db"
)

# Initialize Chroma client (local embedded)
client = chromadb.Client(settings=settings)

# Create or get collection for workouts
collection_name = "workouts"
try: 
    collection = client.get_collection(name=collection_name)
except Exception:
    collection = client.create_collection(name=collection_name)


def add_workout_chunks(chunks: list[str], embeddings: list[list[float]], metadatas: list[dict] = None):
    """
    Add workout chunks and their embeddings to the Chroma collection.
    """
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    if metadatas is None:
        metadatas = [{"source": "upload"} for _ in chunks]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )

def query_workouts(question: str, collection, n_results=5):
    question_embedding = embed_texts([question])[0]
    results = collection.query(query_embeddings=[question_embedding], n_results=n_results, include=["documents", "metadatas"])
    return results

def get_collection():
    try:
        return client.get_collection(name=collection_name)
    except Exception:
        return client.create_collection(name=collection_name)