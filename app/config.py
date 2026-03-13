import os


def load_config():
    # В Docker-окружении load_dotenv() не нужен, 
    # переменные передаются напрямую через docker run --env-file
    
    # Список клиентов для мультитендантности
    clients = []
    
    # Дефолтный клиент (NEXT) - для обратной совместимости
    next_client = {
        "id": "next",
        "name": "NEXT",
        "wb_api_key": os.getenv("WB_API_KEY"),
        "ozon_client_id": os.getenv("OZON_CLIENT_ID"),
        "ozon_api_key": os.getenv("OZON_API_KEY"),
        "qdrant_collection": os.getenv("QDRANT_COLLECTION", "smart_bot_knowledge"),
        "knowledge_base_path": "knowledge_base.md",
        "telegram_enabled": bool(os.getenv("TELETHON_API_ID") and os.getenv("TELETHON_API_HASH"))
    }
    
    if next_client["wb_api_key"] or (next_client["ozon_client_id"] and next_client["ozon_api_key"]):
        clients.append(next_client)
        
    # Возможность загрузить дополнительных клиентов через JSON
    import json
    extra_clients_json = os.getenv("EXTRA_CLIENTS_JSON")
    if extra_clients_json:
        try:
            extra_clients = json.loads(extra_clients_json)
            clients.extend(extra_clients)
        except Exception as e:
            import logging
            logging.error(f"Ошибка парсинга EXTRA_CLIENTS_JSON: {e}")

    return {
        "CLIENTS": clients,
        "TELETHON_API_ID": os.getenv("TELETHON_API_ID"),
        "TELETHON_API_HASH": os.getenv("TELETHON_API_HASH"),
        "TELETHON_PHONE": os.getenv("TELETHON_PHONE"),
        "TELEGRAM_PASSWORD": os.getenv("TELEGRAM_PASSWORD"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "OPENAI_API_BASE": os.getenv("OPENAI_API_BASE"),
        "OPENAI_MODEL_NAME": os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
        "WB_CHAT_POLLING_INTERVAL_SECONDS": int(os.getenv("WB_CHAT_POLLING_INTERVAL_SECONDS", 15)),
        "WB_CHECK_INTERVAL_SECONDS": int(os.getenv("WB_CHECK_INTERVAL_SECONDS", 300)),
        "WB_CHAT_DEBUG": os.getenv("WB_CHAT_DEBUG", "false").lower() in ('true', '1', 't'),
        "TELEGRAM_MESSAGE_DELAY_SECONDS": int(os.getenv("TELEGRAM_MESSAGE_DELAY_SECONDS", 2)),
        "OZON_CHECK_INTERVAL_SECONDS": int(os.getenv("OZON_CHECK_INTERVAL_SECONDS", 300)),
        "OZON_CHAT_POLLING_INTERVAL_SECONDS": int(os.getenv("OZON_CHAT_POLLING_INTERVAL_SECONDS", 60)),
        "LANGFUSE_PUBLIC_KEY": os.getenv("LANGFUSE_PUBLIC_KEY"),
        "LANGFUSE_SECRET_KEY": os.getenv("LANGFUSE_SECRET_KEY"),
        "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    }


