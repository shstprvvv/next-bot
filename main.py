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
    69|    # 0. Загрузка переменных окружения (для локального запуска)
    70|    load_dotenv()
    71|
    72|    # 1. Настройка логирования
    73|    setup_logging()
    74|    logging.info("[Main] Запуск AI Support Bot (Clean Architecture)...")
    75|    
    76|    # 2. Загрузка конфига
    77|    cfg = load_config()
    78|
    79|    loop = asyncio.get_running_loop()
    80|    stop_event = asyncio.Event()
    81|    cleanup_started = False
    82|
    83|    def _loop_exception_handler(_loop, context):
    84|        msg = context.get("message", "Unhandled exception in event loop")
    85|        exc = context.get("exception")
    86|        logging.critical(f"[Asyncio] {msg}: {exc}", exc_info=exc)
    87|
    88|    loop.set_exception_handler(_loop_exception_handler)
    89|    
    90|    # 3. Инициализация общих Адаптеров
    91|    logging.info("[Main] Инициализация общих адаптеров...")
    92|    
    93|    # LLM (общий для всех клиентов)
    94|    llm_adapter = LangChainLLMAdapter(
    95|        api_key=cfg.get("OPENAI_API_KEY"),
    96|        base_url=cfg.get("OPENAI_API_BASE"),
    97|        model_name=cfg.get("OPENAI_MODEL_NAME"),
    98|        temperature=0.0
    99|    )
   100|    
   101|    # Database (общий)
   102|    db_adapter = DatabaseAdapter(db_path="sessions/smart_bot.db")
   103|
   104|    # Список всех запущенных воркеров и задач
   105|    all_workers = []
   106|    all_tasks = []
   107|    all_clients = [] # Для Telegram
   108|
   109|    # 4. Итерация по клиентам и инициализация их воркеров
   110|    clients_cfg = cfg.get("CLIENTS", [])
   111|    logging.info(f"[Main] Найдено конфигураций клиентов: {len(clients_cfg)}")
   112|
   113|    for client in clients_cfg:
   114|        client_id = client["id"]
   115|        client_name = client["name"]
   116|        logging.info(f"[Main] Инициализация клиента: {client_name} ({client_id})...")
   117|
   118|        # Специфичный для клиента Retriever
   119|        retriever = QdrantRetrieverAdapter(
   120|            collection_name=client.get("qdrant_collection", f"kb_{client_id}"),
   121|            knowledge_base_path=client.get("knowledge_base_path", "knowledge_base.md"),
   122|            openai_api_key=cfg.get("OPENAI_API_KEY"),
   123|            openai_api_base=cfg.get("OPENAI_API_BASE")
   124|        )
   125|
   126|        # Специфичные для клиента Use Cases
   127|        answer_use_case = AnswerQuestionUseCase(llm=llm_adapter, retriever=retriever)
   128|        feedback_use_case = ReplyToFeedbackUseCase(llm=llm_adapter, retriever=retriever)
   129|
   130|        # --- Wildberries ---
   131|        wb_key = client.get("wb_api_key")
   132|        if wb_key:
   133|            logging.info(f"[{client_name}] Подключение к Wildberries...")
   134|            wb_client = WBClient(api_key=wb_key)
   135|            
   136|            check_interval = cfg.get("WB_CHECK_INTERVAL_SECONDS", 300)
   137|            
   138|            w_q = WBQuestionsWorker(wb_client, answer_use_case, check_interval, ignore_older_than_days=30)
   139|            w_f = WBFeedbacksWorker(wb_client, feedback_use_case, check_interval, ignore_older_than_days=30)
   140|            w_c = WBChatWorker(wb_client, answer_use_case, cfg.get("WB_CHAT_POLLING_INTERVAL_SECONDS", 15))
   141|            
   142|            all_workers.extend([w_q, w_f, w_c])
   143|            all_tasks.append(asyncio.create_task(w_q.start(), name=f"wb_q_{client_id}"))
   144|            all_tasks.append(asyncio.create_task(w_f.start(), name=f"wb_f_{client_id}"))
   145|            all_tasks.append(asyncio.create_task(w_c.start(), name=f"wb_c_{client_id}"))
   146|
   147|        # --- Ozon ---
   148|        oz_id = client.get("ozon_client_id")
   149|        oz_key = client.get("ozon_api_key")
   150|        if oz_id and oz_key:
   151|            logging.info(f"[{client_name}] Подключение к Ozon...")
   152|            ozon_client = OzonClient(client_id=oz_id, api_key=oz_key)
   153|            
   154|            check_interval = cfg.get("OZON_CHECK_INTERVAL_SECONDS", 300)
   155|            
   156|            w_q = OzonQuestionsWorker(ozon_client, answer_use_case, db_adapter, check_interval)
   157|            w_r = OzonReviewsWorker(ozon_client, feedback_use_case, db_adapter, check_interval)
   158|            w_c = OzonChatWorker(ozon_client, db_adapter, answer_use_case, cfg.get("OZON_CHAT_POLLING_INTERVAL_SECONDS", 60))
   159|            
   160|            all_workers.extend([w_q, w_r, w_c])
   161|            all_tasks.append(asyncio.create_task(w_q.start(), name=f"oz_q_{client_id}"))
   162|            all_tasks.append(asyncio.create_task(w_r.start(), name=f"oz_r_{client_id}"))
   163|            all_tasks.append(asyncio.create_task(w_c.start(), name=f"oz_c_{client_id}"))
   164|
   165|        # --- Telegram --- (Пока только для первого клиента, так как API ID/HASH обычно одни на сессию)
   166|        if client.get("telegram_enabled") and not all_clients:
   167|            t_id = cfg.get("TELETHON_API_ID")
   168|            t_hash = cfg.get("TELETHON_API_HASH")
   169|            if t_id and t_hash:
   170|                logging.info(f"[{client_name}] Подключение к Telegram...")
   171|                t_client = create_telegram_client(
   172|                    session_name=os.getenv('TELETHON_SESSION_NAME', 'sessions/user_session'),
   173|                    api_id=t_id,
   174|                    api_hash=t_hash
   175|                )
   176|                telegram_adapter = TelegramAdapter(t_client, answer_use_case, cfg.get("TELEGRAM_MESSAGE_DELAY_SECONDS", 2))
   177|                all_clients.append(t_client)
   178|
   179|    # 6. Основной цикл
   180|    async def shutdown():
   181|        nonlocal cleanup_started
   182|        if cleanup_started: return
   183|        cleanup_started = True
   184|        logging.info("[Main] Завершаю работу...")
   185|        stop_event.set()
   186|        for w in all_workers: w.stop()
   187|        for t in all_tasks: t.cancel()
   188|        for c in all_clients: await c.disconnect()
   189|
   190|    for sig in (signal.SIGINT, signal.SIGTERM):
   191|        try: loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
   192|        except NotImplementedError: pass
   193|
   194|    if all_clients:
   195|        phone = cfg.get("TELETHON_PHONE")
   196|        password = cfg.get("TELEGRAM_PASSWORD")
   197|        logging.info(f"[Main] Старт Telegram (phone={phone})...")
   198|        while not stop_event.is_set():
   199|            try:
   200|                await all_clients[0].start(phone=phone, password=password)
   201|                await all_clients[0].run_until_disconnected()
   202|                if stop_event.is_set(): break
   203|                await asyncio.sleep(5)
   204|            except Exception as e:
   205|                logging.error(f"[Main] Ошибка Telegram: {e}")
   206|                await asyncio.sleep(5)
   207|    else:
   208|        logging.info("[Main] Работа в режиме маркетплейсов.")
   209|        while not stop_event.is_set():
   210|            await asyncio.sleep(1)
   211|
   212|    await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[Main] Остановка бота...")
    except Exception as e:
        logging.critical(f"[Main] Критическая ошибка: {e}", exc_info=True)
