import os
import logging
from typing import List
from fastapi import UploadFile
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.adapters.retriever.qdrant_adapter import QdrantRetrieverAdapter
from app.core.config.bots_registry import BOTS_REGISTRY

logger = logging.getLogger(__name__)

class KnowledgeManager:
    """
    Сервис для загрузки и обработки файлов в базу знаний бота (Qdrant).
    """
    def __init__(self, openai_api_key: str, openai_api_base: str):
        self.openai_api_key = openai_api_key
        self.openai_api_base = openai_api_base

    async def process_and_vectorize_file(self, bot_id: str, file_path: str, filename: str) -> int:
        """
        Читает файл, разбивает на чанки и сохраняет в Qdrant коллекцию бота.
        Возвращает количество созданных чанков.
        """
        if bot_id not in BOTS_REGISTRY:
            raise ValueError(f"Бот {bot_id} не найден в реестре.")
            
        bot_config = BOTS_REGISTRY[bot_id]
        collection_name = bot_config["collection_name"]
        
        # 1. Извлекаем текст (Extract)
        docs = self._load_document(file_path, filename)
        if not docs:
            raise ValueError("Не удалось извлечь текст из файла или файл пуст.")

        # 2. Разбиваем на куски (Transform)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_documents(docs)
        
        # Добавляем метаданные источника к каждому чанку
        for chunk in chunks:
            chunk.metadata["source_file"] = filename

        logger.info(f"[KnowledgeManager] Файл {filename} разбит на {len(chunks)} чанков.")

        # 3. Сохраняем в Qdrant (Load)
        retriever = QdrantRetrieverAdapter(
            collection_name=collection_name,
            knowledge_base_path="", # Нам не нужен локальный файл для ребилда здесь
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_api_base
        )
        
        # Добавляем документы в существующую коллекцию
        if retriever.vector_store:
            retriever.vector_store.add_documents(chunks)
            logger.info(f"[KnowledgeManager] {len(chunks)} чанков успешно добавлены в коллекцию {collection_name}.")
        else:
            raise RuntimeError("Векторное хранилище не инициализировано.")
            
        return len(chunks)

    def _load_document(self, file_path: str, filename: str) -> List:
        """Выбирает правильный лоадер в зависимости от расширения файла."""
        import pandas as pd
        
        ext = filename.lower().split('.')[-1]
        
        try:
            if ext == 'pdf':
                loader = PyPDFLoader(file_path)
                return loader.load()
            elif ext in ['txt', 'md', 'csv']:
                loader = TextLoader(file_path, encoding='utf-8')
                return loader.load()
            elif ext in ['xlsx', 'xls']:
                # Читаем Excel файл с помощью pandas
                df = pd.read_excel(file_path)
                df = df.fillna("") # Заменяем пустые значения на пустые строки
                
                docs = []
                for index, row in df.iterrows():
                    row_text_parts = []
                    # Проходим по всем колонкам
                    for col_name, val in row.items():
                        val_str = str(val).strip()
                        if val_str:
                            row_text_parts.append(f"{col_name}: {val_str}")
                    
                    # Если строка не пустая, создаем из нее документ
                    if row_text_parts:
                        text_content = "Запись из таблицы: " + " | ".join(row_text_parts)
                        docs.append(Document(
                            page_content=text_content,
                            metadata={"source": filename, "row": index + 1}
                        ))
                return docs
            else:
                raise ValueError(f"Формат файла .{ext} пока не поддерживается.")
        except Exception as e:
            logger.error(f"[KnowledgeManager] Ошибка при чтении файла {filename}: {e}")
            raise

    async def sync_wb_products(self, bot_id: str, wb_api_key: str) -> int:
        """
        Загружает товары из Wildberries и добавляет их в базу знаний.
        """
        from app.adapters.channels.wildberries.client import WBClient
        if bot_id not in BOTS_REGISTRY:
            raise ValueError(f"Бот {bot_id} не найден в реестре.")
            
        bot_config = BOTS_REGISTRY[bot_id]
        collection_name = bot_config["collection_name"]
        
        wb_client = WBClient(api_key=wb_api_key)
        try:
            # Получаем карточки товаров (используем метод content/v2/get/cards/list)
            # Так как в текущем WBClient нет этого метода, сделаем прямой запрос
            url = "https://suppliers-api.wildberries.ru/content/v2/get/cards/list"
            payload = {
                "settings": {
                    "cursor": {
                        "limit": 100
                    },
                    "filter": {
                        "withPhoto": -1
                    }
                }
            }
            
            data = await wb_client._request_json("POST", url, json=payload)
            if not data or "cards" not in data:
                logger.warning("[KnowledgeManager] Не удалось получить карточки товаров WB или список пуст.")
                return 0
                
            cards = data.get("cards", [])
            docs = []
            
            for card in cards:
                nm_id = card.get("nmID", "")
                vendor_code = card.get("vendorCode", "")
                title = card.get("title", "")
                description = card.get("description", "")
                
                # Собираем характеристики
                characteristics = []
                for char in card.get("characteristics", []):
                    for k, v in char.items():
                        characteristics.append(f"{k}: {v}")
                
                char_text = ", ".join(characteristics)
                
                text = f"Товар Wildberries.\nНазвание: {title}\nАртикул продавца: {vendor_code}\nАртикул WB (nmID): {nm_id}\nОписание: {description}\nХарактеристики: {char_text}"
                
                docs.append(Document(
                    page_content=text,
                    metadata={"source": "wildberries", "nmID": nm_id, "vendorCode": vendor_code}
                ))
                
            if not docs:
                return 0
                
            # Сохраняем в Qdrant
            retriever = QdrantRetrieverAdapter(
                collection_name=collection_name,
                knowledge_base_path="",
                openai_api_key=self.openai_api_key,
                openai_api_base=self.openai_api_base
            )
            
            if retriever.vector_store:
                retriever.vector_store.add_documents(docs)
                logger.info(f"[KnowledgeManager] {len(docs)} товаров WB успешно добавлены в коллекцию {collection_name}.")
            else:
                raise RuntimeError("Векторное хранилище не инициализировано.")
                
            return len(docs)
            
        finally:
            await wb_client.aclose()

    async def sync_ozon_products(self, bot_id: str, ozon_client_id: str, ozon_api_key: str) -> int:
        """
        Загружает товары из Ozon и добавляет их в базу знаний.
        """
        from app.adapters.channels.ozon.client import OzonClient
        if bot_id not in BOTS_REGISTRY:
            raise ValueError(f"Бот {bot_id} не найден в реестре.")
            
        bot_config = BOTS_REGISTRY[bot_id]
        collection_name = bot_config["collection_name"]
        
        ozon_client = OzonClient(client_id=ozon_client_id, api_key=ozon_api_key)
        
        # 1. Получаем список ID товаров
        url_list = "/v2/product/list"
        payload_list = {
            "filter": {
                "visibility": "ALL"
            },
            "limit": 100
        }
        
        data_list = await ozon_client._make_request("POST", url_list, json_data=payload_list)
        if not data_list or "result" not in data_list or not data_list["result"].get("items"):
            logger.warning("[KnowledgeManager] Не удалось получить список товаров Ozon или он пуст.")
            return 0
            
        product_ids = [item["product_id"] for item in data_list["result"]["items"]]
        
        # 2. Получаем подробную информацию по ID
        url_info = "/v2/product/info/list"
        payload_info = {
            "product_id": product_ids
        }
        
        data_info = await ozon_client._make_request("POST", url_info, json_data=payload_info)
        if not data_info or "result" not in data_info or not data_info["result"].get("items"):
            logger.warning("[KnowledgeManager] Не удалось получить детали товаров Ozon.")
            return 0
            
        items = data_info["result"]["items"]
        docs = []
        
        for item in items:
            product_id = item.get("id", "")
            offer_id = item.get("offer_id", "")
            name = item.get("name", "")
            price = item.get("price", "")
            
            text = f"Товар Ozon.\nНазвание: {name}\nАртикул продавца (offer_id): {offer_id}\nID товара Ozon: {product_id}\nЦена: {price}"
            
            docs.append(Document(
                page_content=text,
                metadata={"source": "ozon", "product_id": product_id, "offer_id": offer_id}
            ))
            
        if not docs:
            return 0
            
        # Сохраняем в Qdrant
        retriever = QdrantRetrieverAdapter(
            collection_name=collection_name,
            knowledge_base_path="",
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_api_base
        )
        
        if retriever.vector_store:
            retriever.vector_store.add_documents(docs)
            logger.info(f"[KnowledgeManager] {len(docs)} товаров Ozon успешно добавлены в коллекцию {collection_name}.")
        else:
            raise RuntimeError("Векторное хранилище не инициализировано.")
            
        return len(docs)
