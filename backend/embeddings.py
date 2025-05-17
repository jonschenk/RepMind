from sentence_transformers import SentenceTransformer
import numpy as np

# Load the DeepSeek embedding model from HuggingFace
model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings into dense vectors using DeepSeek embeddings.
    """
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()