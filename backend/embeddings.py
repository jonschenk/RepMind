from sentence_transformers import SentenceTransformer
from langchain.embeddings.base import Embeddings

class CustomEmbeddings(Embeddings):
    def __init__(self):
        self.model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

# Create instance to be imported
embedding_model = CustomEmbeddings()