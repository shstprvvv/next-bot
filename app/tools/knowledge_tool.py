import logging
import os
from langchain.tools import Tool
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter


def create_retriever(api_key: str, base_url: str = None):
    """Создает и возвращает retriever из knowledge_base.md. В случае ошибки возвращает None."""
    logging.info("[Retriever] Инициализация retriever из Markdown...")
    try:
        logging.info("[Retriever] Шаг 1: Загрузка knowledge_base.md...")
        loader = TextLoader('knowledge_base.md', encoding='utf-8')
        documents = loader.load()
        logging.info("[Retriever] Шаг 1: Файл успешно загружен.")

        logging.info("[Retriever] Шаг 2: Разделение текста по заголовкам Markdown...")
        headers_to_split_on = [
            ("#", "product"),
            ("##", "category"),
            ("###", "subcategory"),
            ("####", "question"),
        ]
        text_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)
        docs = text_splitter.split_text(documents[0].page_content)

        if not docs:
            logging.warning("[Retriever] Не найдено заголовков для разделения. Использую RecursiveCharacterTextSplitter.")
            docs = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100).split_documents(documents)

        logging.info(f"[Retriever] Шаг 2: Текст разделен на {len(docs)} чанков.")

        logging.info("[Retriever] Шаг 3: Создание эмбеддингов и векторной базы...")
        model_name = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
        logging.info(f"[Retriever] Использую модель эмбеддингов: {model_name}")
        embeddings = OpenAIEmbeddings(model=model_name, openai_api_key=api_key, base_url=base_url)
        vector_store = FAISS.from_documents(docs, embeddings)
        logging.info("[Retriever] Шаг 3: Векторная база успешно создана.")

        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
        logging.info("[Retriever] Retriever успешно инициализирован.")
        return retriever
    except FileNotFoundError:
        logging.error("[Retriever] КРИТИЧЕСКАЯ ОШИБКА: Файл knowledge_base.md не найден.")
        return None
    except Exception as e:
        logging.error(f"[Retriever] КРИТИЧЕСКАЯ ОШИБКА при инициализации: {e}", exc_info=True)
        return None


def create_knowledge_base_tool(retriever):
    """Создает Langchain Tool на основе retriever."""
    if retriever is None:
        logging.warning("[KnowledgeBaseTool] Retriever не инициализирован. Создаю fallback-инструмент.")
        def fallback_func(query: str) -> str:
            return "База знаний временно недоступна."
        return Tool(
            name="KnowledgeBaseSearch",
            func=fallback_func,
            description="Инструмент-заглушка для поиска в базе знаний."
        )

    def search_knowledge_base(query: str) -> str:
        try:
            relevant_docs = retriever.invoke(query)
            context = "\n\n".join([doc.page_content for doc in relevant_docs])
            logging.info(f"[KnowledgeBaseTool] Найдена информация для запроса: '{query}'")
            return context
        except Exception as e:
            logging.error(f"[KnowledgeBaseTool] Ошибка при поиске: {e}")
            return "Произошла ошибка при поиске в базе знаний."

    return Tool(
        name="KnowledgeBaseSearch",
        func=search_knowledge_base,
        description="Всегда используй этот инструмент для поиска ответов на любые вопросы о продукте, его характеристиках, функциях, проблемах, доставке или возвратах. Передавай в него исходный вопрос пользователя без изменений."
    )


