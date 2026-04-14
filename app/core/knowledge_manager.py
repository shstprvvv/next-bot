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
        Поддерживает пагинацию (до 10000+ товаров) и удаляет старые товары перед синхронизацией.
        """
        from app.adapters.channels.wildberries.client import WBClient
        if bot_id not in BOTS_REGISTRY:
            raise ValueError(f"Бот {bot_id} не найден в реестре.")
            
        bot_config = BOTS_REGISTRY[bot_id]
        collection_name = bot_config["collection_name"]
        
        # Сначала удаляем старые товары WB из базы
        retriever = QdrantRetrieverAdapter(
            collection_name=collection_name,
            knowledge_base_path="",
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_api_base
        )
        retriever.delete_by_source("wildberries")
        
        wb_client = WBClient(api_key=wb_api_key)
        total_synced = 0
        
        try:
            url = "https://suppliers-api.wildberries.ru/content/v2/get/cards/list"
            
            # Настройки для пагинации
            limit = 100
            updated_at = ""
            nm_id = 0
            
            while True:
                payload = {
                    "settings": {
                        "cursor": {
                            "limit": limit
                        },
                        "filter": {
                            "withPhoto": -1
                        }
                    }
                }
                
                # Добавляем курсор, если это не первый запрос
                if updated_at:
                    payload["settings"]["cursor"]["updatedAt"] = updated_at
                    payload["settings"]["cursor"]["nmID"] = nm_id
                
                data = await wb_client._request_json("POST", url, json=payload)
                if not data or "cards" not in data or not data["cards"]:
                    break # Карточки закончились
                    
                cards = data.get("cards", [])
                docs = []
                
                for card in cards:
                    current_nm_id = card.get("nmID", "")
                    vendor_code = card.get("vendorCode", "")
                    title = card.get("title", "")
                    description = card.get("description", "")
                    
                    # Собираем характеристики
                    characteristics = []
                    for char in card.get("characteristics", []):
                        for k, v in char.items():
                            characteristics.append(f"{k}: {v}")
                    
                    char_text = ", ".join(characteristics)
                    
                    text = f"Товар Wildberries.\nНазвание: {title}\nАртикул продавца: {vendor_code}\nАртикул WB (nmID): {current_nm_id}\nОписание: {description}\nХарактеристики: {char_text}"
                    
                    docs.append(Document(
                        page_content=text,
                        metadata={"source": "wildberries", "doc_type": "product", "nmID": current_nm_id, "vendorCode": vendor_code}
                    ))
                
                if docs and retriever.vector_store:
                    # Генерируем детерминированные ID для векторов
                    import uuid
                    ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"wb_{bot_id}_{doc.metadata['nmID']}")) for doc in docs]
                    retriever.vector_store.add_documents(docs, ids=ids)
                    total_synced += len(docs)
                    logger.info(f"[KnowledgeManager] Загружен батч из {len(docs)} товаров WB. Всего: {total_synced}")
                
                # Обновляем курсор для следующего запроса
                cursor = data.get("cursor", {})
                updated_at = cursor.get("updatedAt")
                nm_id = cursor.get("nmID")
                
                if not updated_at:
                    break # Если API не вернул курсор, заканчиваем
                    
            logger.info(f"[KnowledgeManager] Синхронизация WB завершена. Всего товаров: {total_synced}")
            return total_synced
            
        finally:
            await wb_client.aclose()

    async def sync_ozon_products(self, bot_id: str, ozon_client_id: str, ozon_api_key: str) -> int:
        """
        Загружает товары из Ozon и добавляет их в базу знаний.
        Поддерживает пагинацию (до 10000+ товаров) и удаляет старые товары перед синхронизацией.
        """
        from app.adapters.channels.ozon.client import OzonClient
        if bot_id not in BOTS_REGISTRY:
            raise ValueError(f"Бот {bot_id} не найден в реестре.")
            
        bot_config = BOTS_REGISTRY[bot_id]
        collection_name = bot_config["collection_name"]
        
        # Сначала удаляем старые товары Ozon из базы
        retriever = QdrantRetrieverAdapter(
            collection_name=collection_name,
            knowledge_base_path="",
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_api_base
        )
        retriever.delete_by_source("ozon")
        
        ozon_client = OzonClient(client_id=ozon_client_id, api_key=ozon_api_key)
        total_synced = 0
        
        # 1. Получаем список ВСЕХ ID товаров с пагинацией
        url_list = "/v2/product/list"
        all_product_ids = []
        last_id = ""
        
        while True:
            payload_list = {
                "filter": {
                    "visibility": "ALL"
                },
                "limit": 1000,
                "last_id": last_id
            }
            
            data_list = await ozon_client._make_request("POST", url_list, json_data=payload_list)
            if not data_list or "result" not in data_list or not data_list["result"].get("items"):
                break
                
            items = data_list["result"]["items"]
            all_product_ids.extend([item["product_id"] for item in items])
            
            last_id = data_list["result"].get("last_id", "")
            if not last_id:
                break
                
        if not all_product_ids:
            logger.warning("[KnowledgeManager] Не удалось получить список товаров Ozon или он пуст.")
            return 0
            
        logger.info(f"[KnowledgeManager] Получено {len(all_product_ids)} ID товаров Ozon. Начинаем загрузку деталей...")
        
        # 2. Получаем подробную информацию по ID (батчами по 500 штук)
        url_info = "/v2/product/info/list"
        batch_size = 500
        
        for i in range(0, len(all_product_ids), batch_size):
            batch_ids = all_product_ids[i:i+batch_size]
            payload_info = {
                "product_id": batch_ids
            }
            
            data_info = await ozon_client._make_request("POST", url_info, json_data=payload_info)
            if not data_info or "result" not in data_info or not data_info["result"].get("items"):
                continue
                
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
                    metadata={"source": "ozon", "doc_type": "product", "product_id": product_id, "offer_id": offer_id}
                ))
                
            if docs and retriever.vector_store:
                # Генерируем детерминированные ID для векторов
                import uuid
                ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ozon_{bot_id}_{doc.metadata['product_id']}")) for doc in docs]
                retriever.vector_store.add_documents(docs, ids=ids)
                total_synced += len(docs)
                logger.info(f"[KnowledgeManager] Загружен батч из {len(docs)} товаров Ozon. Всего: {total_synced}")
                
        logger.info(f"[KnowledgeManager] Синхронизация Ozon завершена. Всего товаров: {total_synced}")
        return total_synced

    def export_products_to_excel(self, bot_id: str) -> str:
        """
        Экспортирует все товары бота в Excel файл и возвращает путь к нему.
        """
        import pandas as pd
        import uuid
        
        if bot_id not in BOTS_REGISTRY:
            raise ValueError(f"Бот {bot_id} не найден в реестре.")
            
        bot_config = BOTS_REGISTRY[bot_id]
        collection_name = bot_config["collection_name"]
        
        retriever = QdrantRetrieverAdapter(
            collection_name=collection_name,
            knowledge_base_path="",
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_api_base
        )
        
        products = retriever.get_all_products()
        
        data = []
        for p in products:
            meta = p.get("metadata", {})
            content = p.get("content", "")
            
            # Пытаемся извлечь данные из текста, если нет в метаданных
            name = meta.get("name", "")
            article = meta.get("article", meta.get("nmID", meta.get("offer_id", "")))
            price = meta.get("price", "")
            
            if not name and "Название:" in content:
                try:
                    name = content.split("Название:")[1].split("\n")[0].strip()
                except: pass
                
            if not article and "Артикул" in content:
                try:
                    article = content.split("Артикул")[1].split(":")[1].split("\n")[0].strip()
                except: pass
                
            if not price and "Цена:" in content:
                try:
                    price = content.split("Цена:")[1].split("\n")[0].strip()
                except: pass
                
            data.append({
                "ID (Системный)": p.get("id", ""),
                "Название": name,
                "Артикул": article,
                "Цена": price,
                "Описание/Контент": content,
                "Источник": p.get("source", "")
            })
            
        df = pd.DataFrame(data)
        
        os.makedirs("temp_exports", exist_ok=True)
        file_path = f"temp_exports/products_{bot_id}_{uuid.uuid4().hex[:8]}.xlsx"
        df.to_excel(file_path, index=False)
        
        return file_path

    async def import_products_from_excel(self, bot_id: str, file_path: str) -> int:
        """
        Импортирует товары из Excel файла в базу знаний.
        """
        import pandas as pd
        
        if bot_id not in BOTS_REGISTRY:
            raise ValueError(f"Бот {bot_id} не найден в реестре.")
            
        bot_config = BOTS_REGISTRY[bot_id]
        collection_name = bot_config["collection_name"]
        
        retriever = QdrantRetrieverAdapter(
            collection_name=collection_name,
            knowledge_base_path="",
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_api_base
        )
        
        df = pd.read_excel(file_path)
        df = df.fillna("")
        
        docs = []
        ids = []
        
        for index, row in df.iterrows():
            sys_id = str(row.get("ID (Системный)", "")).strip()
            name = str(row.get("Название", "")).strip()
            article = str(row.get("Артикул", "")).strip()
            price = str(row.get("Цена", "")).strip()
            content = str(row.get("Описание/Контент", "")).strip()
            source = str(row.get("Источник", "manual")).strip()
            
            if not source:
                source = "manual"
                
            if not content:
                content = f"Товар.\nНазвание: {name}\nАртикул: {article}\nЦена: {price}"
                
            import uuid
            # Если нет системного ID, генерируем на основе артикула или uuid
            if not sys_id:
                if article:
                    sys_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"manual_{bot_id}_{article}"))
                else:
                    sys_id = str(uuid.uuid4())
                    
            docs.append(Document(
                page_content=content,
                metadata={
                    "source": source,
                    "doc_type": "product",
                    "name": name,
                    "article": article,
                    "price": price
                }
            ))
            ids.append(sys_id)
            
        if docs and retriever.vector_store:
            retriever.vector_store.add_documents(docs, ids=ids)
            logger.info(f"[KnowledgeManager] Импортировано {len(docs)} товаров из Excel.")
            
        return len(docs)
