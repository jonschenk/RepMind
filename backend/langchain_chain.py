from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from backend.vectorstore import vectorstore

all_docs = vectorstore._collection.get() 

class AllDocsRetriever(BaseRetriever):
    def _get_relevant_documents(self, query: str, **kwargs):
        # Convert Chroma's raw documents to LangChain Document format
        documents = [
            Document(
                page_content=doc,
                metadata=metadata
            )
            for doc, metadata in zip(all_docs['documents'], all_docs['metadatas'])
        ]
        return documents

embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")

PERSIST_DIRECTORY = "./chroma_db"
COLLECTION_NAME = "workouts"

print(vectorstore.similarity_search("what leg exercises have I done", k=5))

llm = Ollama(model="deepseek-llm")

template = template = template = """
You are a workout assistant helping someone analyze their past workouts. Include specific dates with each relevant exercise. Be sure to specify the TYPE of lift (dumbbell, barbell, cable, machine, etc if specified) and the orientation of the lift (incline, flat, standing, seated, etc if specified).

Do not include RPE if it is 0, that is a placeholder value.

GIVE DATES WHEN ASKED ABOUT SPECIFIC LIFTS

Use the following context to answer the question.

Context:
{context}

Question:
{question}

Answer:
"""

PROMPT = PromptTemplate(template=template, input_variables=["context", "question"])

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=AllDocsRetriever(),
    return_source_documents=True,
    chain_type="stuff",
    chain_type_kwargs={"prompt": PROMPT}
)

def ask_with_langchain(question: str) -> str:
    response = qa_chain.invoke({"query": question})
    
    print("🔍 Retrieved documents:")
    for doc in response["source_documents"]:
        print(doc.page_content)
    
    return response["result"]