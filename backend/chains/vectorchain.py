from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from backend.vectorstore import get_collection

def get_vector_chain(llm):
    vectorstore = get_collection()
    retriever = vectorstore.as_retriever()
    # Define your specialized prompt
    vector_prompt = PromptTemplate(
        input_variables=["context", "question"],
        template="""
        FIRST THING YOU SAY SHOULD BE "VECTOR CHAIN", THEN CONTINUE:
        
        You are a knowledgeable fitness assistant. Use the provided context to answer the user's question clearly and helpfully.

        Context: {context}
        Question: {question}
        Answer:
        """
    )
    return RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": vector_prompt}
    )