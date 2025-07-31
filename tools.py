import logging
from langchain.tools import Tool
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings

def create_knowledge_base_tool(api_key: str, base_url: str = None):
    """Создает и возвращает RAG-инструмент."""
    logging.info("Инициализация RAG-системы...")
    
    try:
        logging.info("Шаг 1: Загрузка knowledge_base.txt...")
        loader = TextLoader('knowledge_base.txt', encoding='utf-8')
        documents = loader.load()
        logging.info("Шаг 1: Файл успешно загружен.")

        logging.info("Шаг 2: Разделение текста на чанки...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)
        logging.info(f"Шаг 2: Текст разделен на {len(docs)} чанков.")

        logging.info("Шаг 3: Создание эмбеддингов и векторной базы (может занять время)...")
        embeddings = OpenAIEmbeddings(openai_api_key=api_key, base_url=base_url)
        vector_store = FAISS.from_documents(docs, embeddings)
        logging.info("Шаг 3: Векторная база успешно создана.")
        
        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
        logging.info("RAG-система успешно инициализирована и готова к работе.")

    except FileNotFoundError:
        logging.error("КРИТИЧЕСКАЯ ОШИБКА: Файл knowledge_base.txt не найден.")
        return None
    except Exception as e:
        logging.error(f"КРИТИЧЕСКАЯ ОШИБКА при инициализации RAG-системы: {e}", exc_info=True)
        return None

    def search_knowledge_base(query: str) -> str:
        """Ищет релевантную информацию в базе знаний по запросу пользователя."""
        try:
            relevant_docs = retriever.invoke(query)
            context = "\n\n".join([doc.page_content for doc in relevant_docs])
            logging.info(f"Найдена релевантная информация для запроса: '{query}'")
            return context
        except Exception as e:
            logging.error(f"Ошибка при поиске в базе знаний: {e}", exc_info=True)
            return "Произошла ошибка при поиске в базе знаний."

    return Tool(
        name="KnowledgeBaseSearch",
        func=search_knowledge_base,
        description="Всегда используй этот инструмент для поиска ответов на любые вопросы о продукте, его характеристиках, функциях, проблемах, доставке или возвратах. Передавай в него исходный вопрос пользователя без изменений."
    ) 