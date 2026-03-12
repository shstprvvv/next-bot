import os
import logging
import time
from typing import List, Optional
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.ports.retriever import KnowledgeRetriever
from app.core.models.chunk import RetrievedChunk

logger = logging.getLogger(__name__)

class QdrantRetrieverAdapter(KnowledgeRetriever):
    def __init__(self, collection_name: str, knowledge_base_path: str, openai_api_key: Optional[str] = None, openai_api_base: Optional[str] = None):
        self.collection_name = collection_name
        self.knowledge_base_path = knowledge_base_path
        self.openai_api_key = openai_api_key
        self.openai_api_base = openai_api_base
        
        # Получаем URL Qdrant из окружения. Внутри Docker-сети это будет http://qdrant:6333
        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        
        self.embeddings = self._get_embeddings()
        
        # Инициализируем клиент с ретраями на случай, если контейнер Qdrant еще поднимается
        self.client = self._connect_with_retry()
        self.vector_store = self._init_collection_and_store()

    def _get_embeddings(self):
        provider = (os.getenv("EMBEDDINGS_PROVIDER") or "openai").strip().lower()
        
        if not self.openai_api_key and provider == "openai":
            logger.warning("[QdrantAdapter] Нет OpenAI API Key. Переключаюсь на локальные эмбеддинги.")
            provider = "local"

        if provider == "local":
            model_name = os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            logger.info(f"[QdrantAdapter] Использую локальные эмбеддинги: {model_name}")
            return HuggingFaceEmbeddings(model_name=model_name)
        
        model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        logger.info(f"[QdrantAdapter] Использую OpenAI эмбеддинги: {model_name}")
        return OpenAIEmbeddings(
            model=model_name, 
            openai_api_key=self.openai_api_key, 
            base_url=self.openai_api_base
        )

    # Декоратор tenacity: пытаемся подключиться до 7 раз, с экспоненциальной задержкой (от 2 до 10 секунд)
    @retry(
        stop=stop_after_attempt(7),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        reraise=True
    )
    def _connect_with_retry(self) -> QdrantClient:
        logger.info(f"[QdrantAdapter] Попытка подключения к Qdrant по адресу {self.qdrant_url}...")
        client = QdrantClient(url=self.qdrant_url, timeout=10.0)
        # Делаем тестовый запрос, чтобы убедиться, что база реально отвечает
        client.get_collections()
        logger.info("[QdrantAdapter] Успешное подключение к Qdrant!")
        return client

    def _init_collection_and_store(self):
        # Проверяем, существует ли коллекция
        collections = self.client.get_collections().collections
        collection_exists = any(c.name == self.collection_name for c in collections)
        
        # Узнаем размерность эмбеддингов, создав тестовый вектор
        test_embedding = self.embeddings.embed_query("test")
        vector_size = len(test_embedding)

        if not collection_exists:
            logger.info(f"[QdrantAdapter] Коллекция {self.collection_name} не найдена. Создаю новую...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            
            # Загружаем данные из текущего knowledge_base.md
            self._rebuild_index()
        else:
            logger.info(f"[QdrantAdapter] Подключение к существующей коллекции {self.collection_name}.")

        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
        )

    def _rebuild_index(self):
        logger.info("[QdrantAdapter] Начало загрузки документов в базу...")
        try:
            loader = TextLoader(self.knowledge_base_path, encoding='utf-8')
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

            logger.info(f"[QdrantAdapter] Создание векторов для {len(docs)} чанков...")
            
            # В Qdrant мы просто добавляем документы через LangChain обертку
            QdrantVectorStore.from_documents(
                docs,
                self.embeddings,
                url=self.qdrant_url,
                collection_name=self.collection_name,
                force_recreate=True # Пересоздаем коллекцию при ребилде
            )
            logger.info("[QdrantAdapter] Документы успешно загружены в Qdrant.")
            
        except Exception as e:
            logger.critical(f"[QdrantAdapter] Критическая ошибка при загрузке документов: {e}", exc_info=True)

    def retrieve(self, query: str, k: int = 6) -> List[RetrievedChunk]:
        if not self.vector_store:
            logger.error("[QdrantAdapter] Векторное хранилище не инициализировано.")
            return []

        try:
            # QdrantVectorStore поддерживает MMR
            docs = self.vector_store.max_marginal_relevance_search(
                query, 
                k=k, 
                fetch_k=20, 
                lambda_mult=0.7
            )
            
            return [
                RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata
                ) for doc in docs
            ]
        except Exception as e:
            logger.error(f"[QdrantAdapter] Ошибка поиска: {e}")
            return []