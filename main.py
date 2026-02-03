import os
import logging
import asyncio
from datetime import datetime

from app.config import load_config
from app.logging_config import setup_logging

# Core
from app.core.use_cases.answer_question import AnswerQuestionUseCase

# Adapters
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.faiss_adapter import FAISSRetrieverAdapter
from app.adapters.channels.telegram_adapter import TelegramAdapter
from app.adapters.channels.wildberries.client import WBClient
from app.adapters.channels.wildberries.worker import WBQuestionsWorker

# Telegram Client (старый, но рабочий)
from app.telegram.client import create_telegram_client

async def main():
    # 1. Настройка логирования
    setup_logging()
    logging.info("[Main] Запуск AI Support Bot (Clean Architecture)...")
    
    # 2. Загрузка конфига
    cfg = load_config()
    
    # 3. Инициализация Адаптеров (Infrastructure Layer)
    logging.info("[Main] Инициализация адаптеров...")
    
    # LLM
    llm_adapter = LangChainLLMAdapter(
        api_key=cfg.get("OPENAI_API_KEY"),
        base_url=cfg.get("OPENAI_API_BASE"),
        model_name="gpt-4o-mini",
        temperature=0.0
    )
    
    # Retriever (FAISS)
    retriever_adapter = FAISSRetrieverAdapter(
        index_path="faiss_index",
        knowledge_base_path="knowledge_base.md",
        openai_api_key=cfg.get("OPENAI_API_KEY"),
        openai_api_base=cfg.get("OPENAI_API_BASE")
    )
    
    # 4. Инициализация Use Cases (Application Layer)
    logging.info("[Main] Сборка Use Cases...")
    answer_use_case = AnswerQuestionUseCase(
        llm=llm_adapter, 
        retriever=retriever_adapter
    )
    
    # 5. Инициализация Каналов (Presentation Layer)
    
    # --- Wildberries ---
    wb_api_key = cfg.get("WB_API_KEY")
    if wb_api_key:
        logging.info("[Main] Подключение к Wildberries (Вопросы)...")
        wb_client = WBClient(api_key=wb_api_key)
        
        # Настройка интервала проверки (по умолчанию 300 сек = 5 мин)
        check_interval = int(cfg.get("WB_CHECK_INTERVAL_SECONDS", 300))
        
        wb_worker = WBQuestionsWorker(
            wb_client=wb_client,
            use_case=answer_use_case,
            check_interval=check_interval,
            ignore_older_than_days=0 # 0 = отвечать только на вопросы, пришедшие после запуска бота
        )
        # Запускаем как фоновую задачу
        asyncio.create_task(wb_worker.start())
    else:
        logging.warning("[Main] WB_API_KEY не найден. Модуль Wildberries отключен.")

    # --- Telegram ---
    logging.info("[Main] Подключение к Telegram...")
    
    telethon_client = create_telegram_client(
        session_name=os.getenv('TELETHON_SESSION_NAME', 'sessions/user_session'),
        api_id=cfg.get("TELETHON_API_ID"),
        api_hash=cfg.get("TELETHON_API_HASH")
    )
    
    # Подключаем наш адаптер к клиенту
    telegram_adapter = TelegramAdapter(
        client=telethon_client,
        use_case=answer_use_case,
        message_delay=cfg.get("TELEGRAM_MESSAGE_DELAY_SECONDS", 2)
    )
    
    # 6. Запуск Telegram (блокирующий вызов в конце)
    phone = cfg.get("TELETHON_PHONE")
    password = cfg.get("TELEGRAM_PASSWORD")
    
    logging.info(f"[Main] Старт клиента Telegram (phone={phone})...")
    
    await telethon_client.start(phone=phone, password=password)
    logging.info("[Main] Бот запущен и готов к работе! 🚀")
    
    await telethon_client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[Main] Остановка бота...")
    except Exception as e:
        logging.critical(f"[Main] Критическая ошибка: {e}", exc_info=True)
