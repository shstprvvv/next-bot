import os
import logging
import asyncio
import signal
from datetime import datetime
from dotenv import load_dotenv

from app.config import load_config
from app.logging_config import setup_logging

# Core
from app.core.use_cases.answer_question import AnswerQuestionUseCase
from app.core.use_cases.reply_to_feedback import ReplyToFeedbackUseCase

# Adapters
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.qdrant_adapter import QdrantRetrieverAdapter
from app.adapters.channels.telegram_adapter import TelegramAdapter
from app.adapters.channels.wildberries.client import WBClient
from app.adapters.channels.wildberries.worker import WBQuestionsWorker, WBFeedbacksWorker, WBChatWorker
from app.adapters.channels.ozon.client import OzonClient
from app.adapters.channels.ozon.worker import OzonQuestionsWorker
from app.adapters.channels.ozon.reviews_worker import OzonReviewsWorker
from app.adapters.channels.ozon.chat_worker import OzonChatWorker
from app.adapters.db.database_adapter import DatabaseAdapter

# Telegram Client (старый, но рабочий)
from app.telegram.client import create_telegram_client


def _validate_config(cfg: dict) -> None:
    # Telegram keys are now optional. If they are missing, Telegram will just be disabled.
    pass

async def main():
    # 0. Загрузка переменных окружения (для локального запуска)
    load_dotenv()

    # 1. Настройка логирования
    setup_logging()
    logging.info("[Main] Запуск AI Support Bot (Clean Architecture)...")
    
    # 2. Загрузка конфига
    cfg = load_config()
    _validate_config(cfg)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    cleanup_started = False

    def _loop_exception_handler(_loop, context):
        msg = context.get("message", "Unhandled exception in event loop")
        exc = context.get("exception")
        logging.critical(f"[Asyncio] {msg}: {exc}", exc_info=exc)

    loop.set_exception_handler(_loop_exception_handler)
    
    # 3. Инициализация Адаптеров (Infrastructure Layer)
    logging.info("[Main] Инициализация адаптеров...")
    
    # LLM
    llm_adapter = LangChainLLMAdapter(
        api_key=cfg.get("OPENAI_API_KEY"),
        base_url=cfg.get("OPENAI_API_BASE"),
        model_name=cfg.get("OPENAI_MODEL_NAME"),
        temperature=0.0
    )
    
    # Retriever (Qdrant)
    retriever_adapter = QdrantRetrieverAdapter(
        collection_name="smart_bot_knowledge",
        knowledge_base_path="knowledge_base.md",
        openai_api_key=cfg.get("OPENAI_API_KEY"),
        openai_api_base=cfg.get("OPENAI_API_BASE")
    )
    
    # Database
    db_adapter = DatabaseAdapter(db_path="sessions/smart_bot.db")
    
    # 4. Инициализация Use Cases (Application Layer)
    logging.info("[Main] Сборка Use Cases...")
    answer_use_case = AnswerQuestionUseCase(
        llm=llm_adapter, 
        retriever=retriever_adapter
    )
    feedback_use_case = ReplyToFeedbackUseCase(
        llm=llm_adapter,
        retriever=retriever_adapter
    )
    
    # 5. Инициализация Каналов (Presentation Layer)
    
    # --- Wildberries ---
    wb_api_key = cfg.get("WB_API_KEY")
    wb_client = None
    wb_tasks: list[asyncio.Task] = []
    wb_questions_worker = None
    wb_feedbacks_worker = None
    wb_chat_worker = None
    if wb_api_key:
        logging.info("[Main] Подключение к Wildberries...")
        wb_client = WBClient(api_key=wb_api_key)
        
        # Настройка интервала проверки (по умолчанию 300 сек = 5 мин)
        check_interval = int(cfg.get("WB_CHECK_INTERVAL_SECONDS", 300))
        
        # Воркер вопросов
        wb_questions_worker = WBQuestionsWorker(
            wb_client=wb_client,
            use_case=answer_use_case,
            check_interval=check_interval,
            ignore_older_than_days=30 # Проверяем вопросы за последние 30 дней
        )
        
        # Воркер отзывов
        wb_feedbacks_worker = WBFeedbacksWorker(
            wb_client=wb_client,
            use_case=feedback_use_case,
            check_interval=check_interval,
            ignore_older_than_days=30 # Проверяем отзывы за последние 30 дней
        )
        
        # Воркер чатов
        wb_chat_worker = WBChatWorker(
            wb_client=wb_client,
            use_case=answer_use_case,
            check_interval=int(cfg.get("WB_CHAT_POLLING_INTERVAL_SECONDS", 15))
        )
        
        # Запускаем как фоновые задачи
        wb_tasks.append(asyncio.create_task(wb_questions_worker.start(), name="wb_questions_worker"))
        wb_tasks.append(asyncio.create_task(wb_feedbacks_worker.start(), name="wb_feedbacks_worker"))
        wb_tasks.append(asyncio.create_task(wb_chat_worker.start(), name="wb_chat_worker"))
    else:
        logging.warning("[Main] WB_API_KEY не найден. Модуль Wildberries отключен.")

    # --- Ozon ---
    ozon_client_id = cfg.get("OZON_CLIENT_ID")
    ozon_api_key = cfg.get("OZON_API_KEY")
    ozon_client = None
    ozon_tasks: list[asyncio.Task] = []
    ozon_questions_worker = None
    ozon_reviews_worker = None
    ozon_chat_worker = None
    
    if ozon_client_id and ozon_api_key:
        logging.info("[Main] Подключение к Ozon...")
        ozon_client = OzonClient(client_id=ozon_client_id, api_key=ozon_api_key)
        
        check_interval = int(cfg.get("OZON_CHECK_INTERVAL_SECONDS", 300))
        
        ozon_questions_worker = OzonQuestionsWorker(
            ozon_client=ozon_client,
            use_case=answer_use_case,
            db_adapter=db_adapter,
            check_interval=check_interval
        )
        
        ozon_reviews_worker = OzonReviewsWorker(
            ozon_client=ozon_client,
            use_case=feedback_use_case,
            db_adapter=db_adapter,
            check_interval=check_interval
        )
        
        ozon_chat_worker = OzonChatWorker(
            ozon_client=ozon_client,
            db_adapter=db_adapter,
            answer_use_case=answer_use_case,
            poll_interval=int(cfg.get("OZON_CHAT_POLLING_INTERVAL_SECONDS", 60))
        )
        
        ozon_tasks.append(asyncio.create_task(ozon_questions_worker.start(), name="ozon_questions_worker"))
        ozon_tasks.append(asyncio.create_task(ozon_reviews_worker.start(), name="ozon_reviews_worker"))
        ozon_tasks.append(asyncio.create_task(ozon_chat_worker.start(), name="ozon_chat_worker"))
    else:
        logging.warning("[Main] OZON_CLIENT_ID или OZON_API_KEY не найдены. Модуль Ozon отключен.")

    # --- Telegram ---
    telethon_client = None
    telethon_api_id = cfg.get("TELETHON_API_ID")
    telethon_api_hash = cfg.get("TELETHON_API_HASH")
    
    if telethon_api_id and telethon_api_hash:
        logging.info("[Main] Подключение к Telegram...")
        
        telethon_client = create_telegram_client(
            session_name=os.getenv('TELETHON_SESSION_NAME', 'sessions/user_session'),
            api_id=telethon_api_id,
            api_hash=telethon_api_hash
        )
        
        # Подключаем наш адаптер к клиенту
        telegram_adapter = TelegramAdapter(
            client=telethon_client,
            use_case=answer_use_case,
            message_delay=cfg.get("TELEGRAM_MESSAGE_DELAY_SECONDS", 2)
        )
    else:
        logging.warning("[Main] Ключи Telegram (TELETHON_API_ID/HASH) не найдены. Telegram отключен.")
    
    # 6. Запуск Telegram (если включен) или вечный цикл для воркеров
    phone = cfg.get("TELETHON_PHONE")
    password = cfg.get("TELEGRAM_PASSWORD")
    
    async def shutdown():
        nonlocal cleanup_started
        if cleanup_started:
            return
        cleanup_started = True
        logging.info("[Main] Получен сигнал остановки. Завершаю работу...")
        stop_event.set()

        if wb_questions_worker is not None:
            wb_questions_worker.stop()
        if wb_feedbacks_worker is not None:
            wb_feedbacks_worker.stop()
        if wb_chat_worker is not None:
            wb_chat_worker.stop()

        if ozon_questions_worker is not None:
            ozon_questions_worker.stop()
        if ozon_reviews_worker is not None:
            ozon_reviews_worker.stop()
        if ozon_chat_worker is not None:
            ozon_chat_worker.stop()

        for t in wb_tasks + ozon_tasks:
            t.cancel()

        if telethon_client is not None:
            try:
                await telethon_client.disconnect()
            except Exception:
                logging.warning("[Main] Ошибка при отключении Telegram клиента.", exc_info=True)

        if wb_client is not None:
            try:
                await wb_client.aclose()
            except Exception:
                logging.warning("[Main] Ошибка при закрытии WB клиента.", exc_info=True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
        except NotImplementedError:
            # например, при некоторых окружениях signal handlers не поддерживаются
            pass

    if telethon_client is not None:
        backoff_s = 3
        logging.info(f"[Main] Старт клиента Telegram (phone={phone})...")
        while not stop_event.is_set():
            try:
                await telethon_client.start(phone=phone, password=password)
                logging.info("[Main] Бот запущен и готов к работе!")
                await telethon_client.run_until_disconnected()

                if stop_event.is_set():
                    break

                logging.warning(f"[Main] Telegram отключился. Переподключение через {backoff_s} сек...")
                await asyncio.sleep(backoff_s)
                backoff_s = min(60, backoff_s * 2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"[Main] Ошибка Telegram цикла: {e}", exc_info=True)
                await asyncio.sleep(backoff_s)
                backoff_s = min(60, backoff_s * 2)
    else:
        # Если Telegram отключен, просто держим основной цикл, пока работают воркеры Ozon и WB
        logging.info("[Main] Telegram отключен. Бот запущен только с воркерами маркетплейсов.")
        while not stop_event.is_set():
            await asyncio.sleep(1)

    await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[Main] Остановка бота...")
    except Exception as e:
        logging.critical(f"[Main] Критическая ошибка: {e}", exc_info=True)
