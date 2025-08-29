from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from app.agents.prompts import get_qa_prompt


def create_conversational_chain(llm, retriever):
    """
    Создает и возвращает ConversationalRetrievalChain.
    """
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True, output_key='answer')

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": get_qa_prompt()},
        return_source_documents=False,  # Не возвращаем источники, чтобы ответ был чище
        verbose=True,
    )
    return chain


