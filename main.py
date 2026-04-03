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

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    cleanup_started = False

    def _loop_exception_handler(_loop, context):
        msg = context.get("message", "Unhandled exception in event loop")
        exc = context.get("exception")
        logging.critical(f"[Asyncio] {msg}: {exc}", exc_info=exc)

    loop.set_exception_handler(_loop_exception_handler)
    
    # 3. Инициализация общих Адаптеров
    logging.info("[Main] Инициализация общих адаптеров...")
    
    # LLM (общий для всех клиентов)
    llm_adapter = LangChainLLMAdapter(
        api_key=cfg.get("OPENAI_API_KEY"),
        base_url=cfg.get("OPENAI_API_BASE"),
        model_name=cfg.get("OPENAI_MODEL_NAME"),
        temperature=0.0
    )
    
    # Database (общий)
    db_adapter = DatabaseAdapter(db_path="sessions/smart_bot.db")

    # Список всех запущенных воркеров и задач
    all_workers = []
    all_tasks = []
    all_clients = [] # Для Telegram

    # Итерация по клиентам и инициализация их воркеров
    clients_cfg = cfg.get("CLIENTS", [])
    logging.info(f"[Main] Найдено конфигураций клиентов: {len(clients_cfg)}")
    
    # Отладочный лог сырой переменной (без вывода ключей)
    extra_raw = os.getenv("EXTRA_CLIENTS_JSON")
    logging.info(f"[Main] Сырая переменная EXTRA_CLIENTS_JSON: {bool(extra_raw)} (длина: {len(extra_raw) if extra_raw else 0})")
    
    # Дополнительный лог для проверки всех переменных окружения (безопасно)
    keys_in_env = [k for k in os.environ.keys() if "CLIENT" in k or "WB" in k or "OZON" in k]
    logging.info(f"[Main] Ключи в env: {keys_in_env}")

    for client in clients_cfg:
        client_id = client["id"]
        client_name = client["name"]
        logging.info(f"[Main] Инициализация клиента: {client_name} ({client_id})...")

        # Специфичный для клиента Retriever
        retriever = QdrantRetrieverAdapter(
            collection_name=client.get("qdrant_collection", f"kb_{client_id}"),
            knowledge_base_path=client.get("knowledge_base_path", "knowledge_base.md"),
            openai_api_key=cfg.get("OPENAI_API_KEY"),
            openai_api_base=cfg.get("OPENAI_API_BASE")
        )

        # Специфичные для клиента Use Cases
        answer_use_case = AnswerQuestionUseCase(llm=llm_adapter, retriever=retriever, client_config=client)
        feedback_use_case = ReplyToFeedbackUseCase(llm=llm_adapter, retriever=retriever, client_config=client)

        # --- Wildberries ---
        wb_key = client.get("wb_api_key")
        if wb_key:
            logging.info(f"[{client_name}] Подключение к Wildberries...")
            wb_client = WBClient(api_key=wb_key)
            
            check_interval = cfg.get("WB_CHECK_INTERVAL_SECONDS", 300)
            
            w_q = WBQuestionsWorker(wb_client, answer_use_case, check_interval, ignore_older_than_days=30)
            w_f = WBFeedbacksWorker(wb_client, feedback_use_case, check_interval, ignore_older_than_days=30)
            w_c = WBChatWorker(wb_client, answer_use_case, cfg.get("WB_CHAT_POLLING_INTERVAL_SECONDS", 15))
            
            all_workers.extend([w_q, w_f, w_c])
            all_tasks.append(asyncio.create_task(w_q.start(), name=f"wb_q_{client_id}"))
            all_tasks.append(asyncio.create_task(w_f.start(), name=f"wb_f_{client_id}"))
            all_tasks.append(asyncio.create_task(w_c.start(), name=f"wb_c_{client_id}"))

        # --- Ozon ---
        oz_id = client.get("ozon_client_id")
        oz_key = client.get("ozon_api_key")
        if oz_id and oz_key:
            logging.info(f"[{client_name}] Подключение к Ozon...")
            ozon_client = OzonClient(client_id=oz_id, api_key=oz_key)
            
            check_interval = cfg.get("OZON_CHECK_INTERVAL_SECONDS", 300)
            
            w_q = OzonQuestionsWorker(ozon_client, answer_use_case, db_adapter, check_interval)
            w_r = OzonReviewsWorker(ozon_client, feedback_use_case, db_adapter, check_interval)
            w_c = OzonChatWorker(ozon_client, db_adapter, answer_use_case, cfg.get("OZON_CHAT_POLLING_INTERVAL_SECONDS", 60))
            
            all_workers.extend([w_q, w_r, w_c])
            all_tasks.append(asyncio.create_task(w_q.start(), name=f"oz_q_{client_id}"))
            all_tasks.append(asyncio.create_task(w_r.start(), name=f"oz_r_{client_id}"))
            all_tasks.append(asyncio.create_task(w_c.start(), name=f"oz_c_{client_id}"))

        # --- Telegram --- (Пока только для первого клиента, так как API ID/HASH обычно одни на сессию)
        if client.get("telegram_enabled") and not all_clients:
            t_id = cfg.get("TELETHON_API_ID")
            t_hash = cfg.get("TELETHON_API_HASH")
            if t_id and t_hash:
                logging.info(f"[{client_name}] Подключение к Telegram...")
                t_client = create_telegram_client(
                    session_name=os.getenv('TELETHON_SESSION_NAME', 'sessions/user_session'),
                    api_id=t_id,
                    api_hash=t_hash
                )
                telegram_adapter = TelegramAdapter(t_client, answer_use_case, cfg.get("TELEGRAM_MESSAGE_DELAY_SECONDS", 2))
                all_clients.append(t_client)

    # 6. Основной цикл
    async def shutdown():
        nonlocal cleanup_started
        if cleanup_started: return
        cleanup_started = True
        logging.info("[Main] Завершаю работу...")
        stop_event.set()
        for w in all_workers: w.stop()
        for t in all_tasks: t.cancel()
        for c in all_clients: await c.disconnect()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
        except NotImplementedError: pass

    # Выводим сообщение о том, какие клиенты были инициализированы
    if not all_workers and not all_clients:
        logging.warning("[Main] ВНИМАНИЕ: Не инициализировано ни одного воркера! Проверьте наличие ключей API в .env.")
    else:
        logging.info(f"[Main] Всего запущено воркеров: {len(all_workers)}. Клиентов Telegram: {len(all_clients)}")

    if all_clients:
        phone = cfg.get("TELETHON_PHONE")
        password = cfg.get("TELEGRAM_PASSWORD")
        logging.info(f"[Main] Старт Telegram (phone={phone})...")
        while not stop_event.is_set():
            try:
                await all_clients[0].start(phone=phone, password=password)
                await all_clients[0].run_until_disconnected()
                if stop_event.is_set(): break
                await asyncio.sleep(5)
            except Exception as e:
                logging.error(f"[Main] Ошибка Telegram: {e}")
                await asyncio.sleep(5)
    else:
        logging.info("[Main] Работа в режиме маркетплейсов.")
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
