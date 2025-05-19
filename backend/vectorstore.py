from langchain_chroma import Chroma
from backend.embeddings import embedding_model
from langchain_core.documents import Document


PERSIST_DIRECTORY = "./chroma_db"
COLLECTION_NAME = "workouts"

vectorstore = Chroma(
    persist_directory=PERSIST_DIRECTORY,
    collection_name=COLLECTION_NAME,
    embedding_function=embedding_model,
)

def add_workout_chunks(chunks: list[str], metadatas: list[dict]):
    """Add workout chunks with their metadata"""
    
    # Convert to Document objects
    documents = [
        Document(
            page_content=chunk,
            metadata=metadata
        )
        for chunk, metadata in zip(chunks, metadatas)
    ]
    
    # Add to vectorstore
    vectorstore.add_documents(documents)

def get_collection():
    return vectorstore