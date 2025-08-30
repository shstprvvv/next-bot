import os
import logging
import asyncio
from collections import deque
from datetime import datetime
# from dotenv import load_dotenv

# # Возвращаем load_dotenv для локального запуска
# load_dotenv()

from app.telegram.client import create_telegram_client
from app.telegram.handlers import setup_telegram_handlers
from app.config import load_config
from app.logging_config import setup_logging
from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from app.tools.knowledge_tool import create_knowledge_base_tool
from app.tools.knowledge_tool import create_retriever
# import aåpp.wb.tools
# from app.wb.background import background_wb_checker, background_wb_chat_responder
import json

from app.chains.factory import create_conversational_chain

# --- Загрузка конфигурации ---
cfg = load_config()
TELETHON_API_ID = cfg.get("TELETHON_API_ID")
TELETHON_API_HASH = cfg.get("TELETHON_API_HASH")
OPENAI_API_KEY = cfg.get("OPENAI_API_KEY")
OPENAI_API_BASE = cfg.get("OPENAI_API_BASE")
WB_API_KEY = cfg.get("WB_API_KEY")
TELEGRAM_MESSAGE_DELAY_SECONDS = cfg.get("TELEGRAM_MESSAGE_DELAY_SECONDS")

# Убираем отладочный вывод, он был нужен для Docker
# --- ОТЛАДОЧНЫЙ ВЫВОД ---
# print("--- [DEBUG] Проверка переменных окружения ---")
# print(f"OPENAI_API_KEY: {'...' + OPENAI_API_KEY[-4:] if OPENAI_API_KEY else 'НЕ УСТАНОВЛЕН'}")
# print(f"OPENAI_API_BASE: {OPENAI_API_BASE or 'НЕ УСТАНОВЛЕН'}")
# print("---------------------------------------------")

# --- Настройка логирования ---
setup_logging()
logging.info("[Main] Конфигурация загружена.")

TELETHON_PHONE = cfg.get("TELETHON_PHONE")
TELEGRAM_PASSWORD = cfg.get("TELEGRAM_PASSWORD")
WB_CHECK_INTERVAL_SECONDS = cfg["WB_CHECK_INTERVAL_SECONDS"]
WB_CHAT_POLLING_INTERVAL_SECONDS = cfg["WB_CHAT_POLLING_INTERVAL_SECONDS"]
WB_CHAT_DEBUG = cfg["WB_CHAT_DEBUG"]


# --- Инициализация LLM и Telegram клиента ---
logging.info("[Main] Инициализация клиентов...")
TELETHON_SESSION_NAME = os.getenv('TELETHON_SESSION_NAME', 'user_session')

# Убедимся, что все необходимые переменные окружения загружены
required_vars = {
    "TELETHON_API_ID": TELETHON_API_ID,
    "TELETHON_API_HASH": TELETHON_API_HASH,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "OPENAI_API_BASE": OPENAI_API_BASE,
    "WB_API_KEY": WB_API_KEY
}
missing_vars = [key for key, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Переменные окружения не установлены: {', '.join(missing_vars)}. Проверьте ваш .env файл.")

client = create_telegram_client(TELETHON_SESSION_NAME, TELETHON_API_ID, TELETHON_API_HASH)
llm = ChatOpenAI(
    model="gpt-4o-mini",
    openai_api_key=OPENAI_API_KEY,
    base_url=OPENAI_API_BASE,
)
logging.info("[Main] Клиенты LLM и Telegram инициализированы.")

# --- Создание retriever ---
logging.info("[Main] Создание retriever для базы знаний...")
retriever = create_retriever(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
if retriever is None:
    logging.critical("[Main] Не удалось создать retriever. Работа приложения невозможна.")
    # В реальном приложении здесь может быть более graceful shutdown
    exit("Retriever initialization failed.")

# --- Функционал WB отключен для экономии средств ---
# wb_tools = [] # Логика WB остается для будущего
# logging.info("[Main] Функционал Wildberries отключен для экономии средств.")


# --- Системные промпты для агента ---
# Больше не нужны, так как промпт теперь внутри Chain
# agent_prompt = get_agent_prompt()


STARTUP_TIME = datetime.now()
logging.info(f"[Main] Время запуска зафиксировано: {STARTUP_TIME.isoformat()}")

# --- Перехват и нормализация ответа перед отправкой ---
FRIENDLY_FALLBACK_MESSAGE = (
    "К сожалению, у меня нет готового решения для вашего вопроса. Мы изучим проблему более детально и вернемся с ответом чуть позже. Приносим извинения за неудобства."
)

BLOCK_PHRASES = [
    "Agent stopped due to iteration limit or time limit",
    "AgentExecutor stopped due to iteration limit",
    "Could not parse LLM output",
    "Tool input is malformed",
    "Invalid or incomplete tool call",
    # Добавим фразы, которые может вернуть chain при отсутствии ответа
    "не знаю ответа",
    "не могу ответить",
]

def _sanitize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    # Убираем стандартные символы разметки и лишние пробелы по краям.
    # Важно: не используем " ".join(cleaned.split()), чтобы сохранить переносы строк.
    cleaned = text.strip().replace("```", "").replace("###", "").replace("---", "").strip()
    return cleaned

def make_final_reply(raw_output: str) -> str:
    cleaned = _sanitize_text(raw_output)
    if not cleaned:
        return FRIENDLY_FALLBACK_MESSAGE
    low = cleaned.lower()
    for phrase in BLOCK_PHRASES:
        if phrase.lower() in low:
            logging.info("[ReplyGuard] Перехвачен служебный или пустой ответ, заменяю на дружелюбный fallback.")
            return FRIENDLY_FALLBACK_MESSAGE
    return cleaned

# --- Управление цепочками и памятью ---
chain_store = {}

def get_or_create_chain(user_id: int):
    if user_id not in chain_store:
        logging.info(f"[Chain] Создание новой цепочки для пользователя {user_id}")
        chain_store[user_id] = create_conversational_chain(llm, retriever)
    return chain_store[user_id]


# --- Фоновая задача для проверки WB (отзывы/вопросы) ---
async def start_background_workers():
    """Фоновые задачи WB отключены для экономии."""
    pass
    # if WB_API_KEY:
    #     asyncio.create_task(
    #         background_wb_checker(
    #             wb_api_key=WB_API_KEY,
    #             get_or_create_agent=get_or_create_agent,
    #             get_unanswered_feedbacks_tool_factory=get_unanswered_feedbacks_tool,
    #             check_interval_seconds=WB_CHECK_INTERVAL_SECONDS,
    #         )
    #     )
    #     asyncio.create_task(
    #         background_wb_chat_responder(
    #             wb_api_key=WB_API_KEY,
    #             get_or_create_agent=get_or_create_agent,
    #             get_chat_events_tool_factory=get_chat_events_tool,
    #             post_chat_message_tool_factory=post_chat_message_tool,
    #             poll_interval_seconds=WB_CHAT_POLLING_INTERVAL_SECONDS,
    #             wb_chat_debug=WB_CHAT_DEBUG,
    #         )
    #     )

# --- Регистрация обработчиков Telegram ---
setup_telegram_handlers(
    client=client,
    message_delay_seconds=TELEGRAM_MESSAGE_DELAY_SECONDS,
    get_or_create_chain=get_or_create_chain,
    normalize_reply=make_final_reply,
)

# --- Запуск приложения ---
async def main():
    """Основная функция для запуска бота и фоновых задач."""
    print("[Main] Запуск Telegram-ассистента...")
    
    # Запускаем фоновые задачи WB
    await start_background_workers()
    
    # Запускаем клиент Telegram
    await client.start(
        phone=TELETHON_PHONE,
        password=TELEGRAM_PASSWORD
    )
    print("[Main] Клиент Telegram запущен.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
