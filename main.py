import os
import logging
import asyncio
from collections import deque
from datetime import datetime

from app.telegram.client import create_telegram_client
from app.telegram.handlers import setup_telegram_handlers
from app.config import load_config
from app.logging_config import setup_logging
from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from app.tools.knowledge_tool import create_knowledge_base_tool
# import aåpp.wb.tools
# from app.wb.background import background_wb_checker, background_wb_chat_responder
import json

from app.agents.factory import create_agent_executor
from app.agents.prompts import get_agent_prompt

# --- Загрузка конфигурации ---
cfg = load_config()
TELETHON_API_ID = cfg.get("TELETHON_API_ID")
TELETHON_API_HASH = cfg.get("TELETHON_API_HASH")
OPENAI_API_KEY = cfg.get("OPENAI_API_KEY")
OPENAI_API_BASE = cfg.get("OPENAI_API_BASE")
WB_API_KEY = cfg.get("WB_API_KEY")
TELEGRAM_MESSAGE_DELAY_SECONDS = cfg.get("TELEGRAM_MESSAGE_DELAY_SECONDS")


# --- Настройка логирования ---
setup_logging()
logging.info("[Main] Конфигурация загружена.")

TELETHON_PHONE = cfg.get("TELETHON_PHONE")
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

# --- Создание инструментов ---
logging.info("[Main] Создание инструментов...")
knowledge_base_tool = create_knowledge_base_tool(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
if knowledge_base_tool is None:
    logging.error("[Main] Не удалось создать инструмент базы знаний. Включаю fallback и продолжаю работу.")
    def _kb_fallback(query: str) -> str:
        return ""
    knowledge_base_tool = Tool(
        name="KnowledgeBaseSearch",
        func=_kb_fallback,
        description="Fallback: возвращает пустой контекст, если база знаний недоступна"
    )

# --- Функционал WB отключен для экономии средств ---
wb_tools = []
logging.info("[Main] Функционал Wildberries отключен для экономии средств.")
# if WB_API_KEY:
#     wb_tools.extend([
#         get_unanswered_feedbacks_tool(),
#         post_feedback_answer_tool(),
#         get_chat_events_tool(),
#         post_chat_message_tool(),
#     ])
#     logging.info("[Main] Инструменты для Wildberries успешно инициализированы.")
# else:
#     logging.warning("[Main] Ключ WB_API_KEY не найден. Функционал Wildberries будет отключен.")

all_tools = [knowledge_base_tool] + wb_tools

# --- Системные промпты для агента ---
agent_prompt = get_agent_prompt()
# wb_agent_prompt = get_wb_agent_prompt() # Отключено


STARTUP_TIME = datetime.now()
logging.info(f"[Main] Время запуска зафиксировано: {STARTUP_TIME.isoformat()}")

# --- Перехват и нормализация ответа перед отправкой ---
FRIENDLY_FALLBACK_MESSAGE = (
    "Извините, сейчас не удалось сформировать ответ. Я уточняю детали и вернусь с решением. "
    "Пока попробуйте: перезагрузить приставку и роутер, проверить интернет. При необходимости можно оформить возврат через маркетплейс."
)

BLOCK_PHRASES = [
    "Agent stopped due to iteration limit or time limit",
    "AgentExecutor stopped due to iteration limit",
    "Could not parse LLM output",
    "Tool input is malformed",
    "Invalid or incomplete tool call",
]

def _sanitize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = text.strip().replace("```", "").strip()
    # Нормализуем пробелы
    cleaned = " ".join(cleaned.split())
    return cleaned

def make_final_reply(raw_output: str) -> str:
    cleaned = _sanitize_text(raw_output)
    if not cleaned:
        return FRIENDLY_FALLBACK_MESSAGE
    low = cleaned.lower()
    for phrase in BLOCK_PHRASES:
        if phrase.lower() in low:
            logging.info("[ReplyGuard] Перехвачен служебный ответ агента, заменяю на дружелюбный fallback.")
            return FRIENDLY_FALLBACK_MESSAGE
    return cleaned

# --- Управление агентами и памятью ---
agent_store = {}

def get_or_create_agent(user_id: int, is_background_agent=False):
    if user_id not in agent_store:
        agent_type = 'фоновых задач' if is_background_agent else f'пользователя {user_id}'
        logging.info(f"[Agent] Создание нового агента для {agent_type}")
        agent_store[user_id] = create_agent_executor(llm, all_tools, is_background_agent=is_background_agent)
    return agent_store[user_id]

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
    get_or_create_agent=get_or_create_agent,
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
        phone=lambda: os.getenv('TELETHON_PHONE'),
        password=lambda: os.getenv('TELEGRAM_PASSWORD')
    )
    print("[Main] Клиент Telegram запущен.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
