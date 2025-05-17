import chromadb
from chromadb.config import Settings


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


def query_similar_chunks(query_embedding: list[float], top_k: int = 5):
    """
    Retrieve top_k similar chunks from the collection given a query embedding.
    """
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    return results["documents"][0]  # list of similar documents