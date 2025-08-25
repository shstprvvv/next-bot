import logging
import os
from langchain.tools import Tool
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings


def create_knowledge_base_tool(api_key: str, base_url: str = None):
    """Создает и возвращает RAG-инструмент. При сбое инициализации возвращает безопасный fallback."""
    logging.info("[KnowledgeBase] Инициализация RAG-системы...")
    retriever = None
    try:
        logging.info("[KnowledgeBase] Шаг 1: Загрузка knowledge_base.txt...")
        loader = TextLoader('knowledge_base.txt', encoding='utf-8')
        documents = loader.load()
        logging.info("[KnowledgeBase] Шаг 1: Файл успешно загружен.")

        logging.info("[KnowledgeBase] Шаг 2: Разделение текста на чанки...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)
        logging.info(f"[KnowledgeBase] Шаг 2: Текст разделен на {len(docs)} чанков.")

        logging.info("[KnowledgeBase] Шаг 3: Создание эмбеддингов и векторной базы...")
        model_name = os.getenv('OPENAI_EMBEDDINGS_MODEL', 'text-embedding-3-small')
        logging.info(f"[KnowledgeBase] Использую модель эмбеддингов: {model_name}")
        embeddings = OpenAIEmbeddings(model=model_name, openai_api_key=api_key, base_url=base_url)
        vector_store = FAISS.from_documents(docs, embeddings)
        logging.info("[KnowledgeBase] Шаг 3: Векторная база успешно создана.")

        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
        logging.info("[KnowledgeBase] RAG-система успешно инициализирована.")

    except FileNotFoundError:
        logging.error("[KnowledgeBase] КРИТИЧЕСКАЯ ОШИБКА: Файл knowledge_base.txt не найден. Переходим в fallback-режим.")
        retriever = None
    except Exception as e:
        logging.error(f"[KnowledgeBase] КРИТИЧЕСКАЯ ОШИБКА при инициализации: {e}", exc_info=True)
        logging.error("[KnowledgeBase] Включен fallback: поиск будет возвращать пустой контекст, приложение продолжит работу.")
        retriever = None

    def search_knowledge_base(query: str) -> str:
        """Ищет релевантную информацию. В fallback-режиме возвращает пустой контекст."""
        try:
            if retriever is None:
                logging.warning("[KnowledgeBase] Fallback-режим: возвращаю пустой контекст для запроса.")
                return ""
            relevant_docs = retriever.invoke(query)
            context = "\n\n".join([doc.page_content for doc in relevant_docs])
            logging.info(f"[KnowledgeBase] Найдена информация для запроса: '{query}'")
            return context
        except Exception as e:
            logging.error(f"[KnowledgeBase] Ошибка при поиске: {e}")
            return ""

    return Tool(
        name="KnowledgeBaseSearch",
        func=search_knowledge_base,
        description="Всегда используй этот инструмент для поиска ответов на любые вопросы о продукте, его характеристиках, функциях, проблемах, доставке или возвратах. Передавай в него исходный вопрос пользователя без изменений."
    )


