import os
import logging
from typing import List, Optional
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from app.core.ports.retriever import KnowledgeRetriever
from app.core.models.chunk import RetrievedChunk

logger = logging.getLogger(__name__)

class FAISSRetrieverAdapter(KnowledgeRetriever):
    def __init__(self, index_path: str, knowledge_base_path: str, openai_api_key: Optional[str] = None, openai_api_base: Optional[str] = None):
        self.index_path = index_path
        self.knowledge_base_path = knowledge_base_path
        self.openai_api_key = openai_api_key
        self.openai_api_base = openai_api_base
        
        self.embeddings = self._get_embeddings()
        self.vector_store = self._load_or_create_index()

    def _get_embeddings(self):
        # Логика выбора эмбеддингов (как в старом коде)
        provider = (os.getenv("EMBEDDINGS_PROVIDER") or "openai").strip().lower()
        
        # Если нет ключа OpenAI, принудительно используем локальные
        if not self.openai_api_key and provider == "openai":
            logger.warning("[FAISSAdapter] Нет OpenAI API Key. Переключаюсь на локальные эмбеддинги.")
            provider = "local"

        if provider == "local":
            model_name = os.getenv("LOCAL_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            logger.info(f"[FAISSAdapter] Использую локальные эмбеддинги: {model_name}")
            return HuggingFaceEmbeddings(model_name=model_name)
        
        model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        logger.info(f"[FAISSAdapter] Использую OpenAI эмбеддинги: {model_name}")
        return OpenAIEmbeddings(
            model=model_name, 
            openai_api_key=self.openai_api_key, 
            base_url=self.openai_api_base
        )

    def _load_or_create_index(self):
        # 1. Попытка загрузить
        if os.path.exists(self.index_path) and os.path.isdir(self.index_path):
            try:
                logger.info(f"[FAISSAdapter] Загрузка индекса из {self.index_path}...")
                return FAISS.load_local(
                    self.index_path, 
                    self.embeddings, 
                    allow_dangerous_deserialization=True
                )
            except Exception as e:
                logger.error(f"[FAISSAdapter] Ошибка загрузки индекса: {e}. Буду пересобирать.")
        
        # 2. Пересборка
        return self._rebuild_index()

    def _rebuild_index(self):
        logger.info("[FAISSAdapter] Начало сборки индекса...")
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
                # Fallback если маркдаун не сработал
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
                docs = text_splitter.split_documents(documents)

            logger.info(f"[FAISSAdapter] Создание векторов для {len(docs)} чанков...")
            vector_store = FAISS.from_documents(docs, self.embeddings)
            
            # Сохраняем
            vector_store.save_local(self.index_path)
            logger.info(f"[FAISSAdapter] Индекс сохранен в {self.index_path}")
            return vector_store
            
        except Exception as e:
            logger.critical(f"[FAISSAdapter] Критическая ошибка при создании индекса: {e}", exc_info=True)
            # В случае ошибки возвращаем пустой индекс (или можно рейзить exception)
            # Для простоты вернем None, но в продакшене лучше Fail Fast
            return None

    def retrieve(self, query: str, k: int = 6) -> List[RetrievedChunk]:
        if not self.vector_store:
            logger.error("[FAISSAdapter] Векторное хранилище не инициализировано.")
            return []

        # Используем MMR для разнообразия
        try:
            docs = self.vector_store.max_marginal_relevance_search(
                query, 
                k=k, 
                fetch_k=20, 
                lambda_mult=0.7
            )
            
            # Конвертируем в наш формат RetrievedChunk
            return [
                RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata
                ) for doc in docs
            ]
        except Exception as e:
            logger.error(f"[FAISSAdapter] Ошибка поиска: {e}")
            return []
