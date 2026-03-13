#!/usr/bin/env python3
"""
Скрипт пересборки базы знаний в Qdrant.
Запускайте после внесения изменений в knowledge_base.md.

Использование:
  Локально:  python rebuild_qdrant_knowledge.py
  В Docker:  docker compose exec bot python rebuild_qdrant_knowledge.py
"""
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_PATH = "knowledge_base.md"
COLLECTION_NAME = "smart_bot_knowledge"
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")


def rebuild_qdrant_index():
    """Пересоздаёт коллекцию в Qdrant и загружает данные из knowledge_base.md."""
    if not os.path.exists(KNOWLEDGE_BASE_PATH):
        logger.error(f"Файл базы знаний не найден: {KNOWLEDGE_BASE_PATH}")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    if not api_key:
        logger.error("OPENAI_API_KEY не задан. Добавьте его в .env")
        sys.exit(1)

    logger.info("Загрузка данных из %s...", KNOWLEDGE_BASE_PATH)
    from langchain_community.document_loaders import TextLoader
    from langchain.text_splitter import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings
    from langchain_qdrant import QdrantVectorStore
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams

    loader = TextLoader(KNOWLEDGE_BASE_PATH, encoding="utf-8")
    documents = loader.load()

    headers_to_split_on = [
        ("#", "product"),
        ("##", "category"),
        ("###", "subcategory"),
        ("####", "question"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)
    docs = markdown_splitter.split_text(documents[0].page_content)

    if not docs:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)

    logger.info("Создание эмбеддингов для %d чанков...", len(docs))
    embeddings = OpenAIEmbeddings(openai_api_key=api_key, base_url=api_base)

    logger.info("Подключение к Qdrant по адресу %s...", QDRANT_URL)
    client = QdrantClient(url=QDRANT_URL, timeout=30.0)

    # Удаляем старую коллекцию, если есть
    collections = client.get_collections().collections
    if any(c.name == COLLECTION_NAME for c in collections):
        logger.info("Удаление старой коллекции %s...", COLLECTION_NAME)
        client.delete_collection(COLLECTION_NAME)

    logger.info("Загрузка документов в Qdrant (force_recreate=True)...")
    QdrantVectorStore.from_documents(
        docs,
        embeddings,
        url=QDRANT_URL,
        collection_name=COLLECTION_NAME,
        force_recreate=True,
    )
    logger.info("База знаний успешно обновлена в Qdrant!")


if __name__ == "__main__":
    rebuild_qdrant_index()
