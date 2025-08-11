import os
import logging
import asyncio
from collections import defaultdict
from datetime import datetime
from telethon import TelegramClient, events
from dotenv import load_dotenv
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from tools import create_knowledge_base_tool, get_unanswered_feedbacks_tool, post_feedback_answer_tool

# --- Настройка логирования (ВАЖНО: должна быть в самом начале) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger('httpx').setLevel(logging.WARNING)

# --- Конфигурация ---
load_dotenv()
TELETHON_API_ID = os.getenv('TELETHON_API_ID')
TELETHON_API_HASH = os.getenv('TELETHON_API_HASH')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE')
WB_API_KEY = os.getenv('WB_API_KEY')
TELEGRAM_PASSWORD = os.getenv('TELEGRAM_PASSWORD')
MESSAGE_DELAY_SECONDS = 30
WB_CHECK_INTERVAL_SECONDS = 900
logging.info("[Main] Конфигурация загружена.")

# --- Инициализация клиентов и моделей ---
client = TelegramClient('user_session', TELETHON_API_ID, TELETHON_API_HASH)
llm = ChatOpenAI(
    model_name="gpt-4o-mini",
    temperature=0.2,
    openai_api_key=OPENAI_API_KEY,
    base_url=OPENAI_API_BASE
)
logging.info("[Main] Клиенты LLM и Telegram инициализированы.")

# --- Создание инструментов ---
knowledge_base_tool = create_knowledge_base_tool(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
if knowledge_base_tool is None:
    logging.error("[Main] Не удалось создать инструмент базы знаний. Приложение не может продолжить работу.")
    exit()

wb_tools = []
if WB_API_KEY:
    # ИСПРАВЛЕНО: Убрана передача STARTUP_TIME, чтобы отвечать на все отзывы
    wb_tools.extend([get_unanswered_feedbacks_tool(), post_feedback_answer_tool()])
    logging.info("[Main] Инструменты для Wildberries успешно инициализированы.")
else:
    logging.warning("[Main] Ключ WB_API_KEY не найден. Функционал Wildberries будет отключен.")

all_tools = [knowledge_base_tool] + wb_tools

# --- Системный промпт для агента ---
# Общий промпт для ответов в Telegram
agent_prompt_template = """Ты — дружелюбный и полезный ассистент техподдержки бренда NEXT.

У тебя есть доступ к этим инструментам:
{tools}

Используй следующий формат:
Thought: Тебе нужно подумать, что делать.
Action: Название одного из инструментов: {tool_names}.
Action Input: Входные данные для инструмента.
Observation: Результат от инструмента.
... (Эта цепочка Thought/Action/Action Input/Observation может повторяться)
Thought: Теперь я знаю финальный ответ.
Final Answer: Финальный ответ для пользователя.

Начинай!

История переписки:
{chat_history}

Вопрос: {input}
{agent_scratchpad}"""

# Специализированный промпт для ответов на отзывы и вопросы в Wildberries
wb_agent_prompt_template = """Ты — ассистент, который отвечает на отзывы и вопросы на Wildberries.

1. Используй `GetUnansweredFeedbacks`, чтобы получить список неотвеченных элементов (и отзывы, и вопросы).
2. Если список пуст, используй `Final Answer: Новых отзывов и вопросов нет.`
3. Если элементы есть, возьми ТОЛЬКО ПЕРВЫЙ.
4. Используй `KnowledgeBaseSearch` с текстом элемента, чтобы найти информацию для ответа.
5. Сгенерируй вежливый, полезный и продающий ответ (можно использовать эмодзи).
6. Используй `PostFeedbackAnswer`, чтобы отправить ответ. В `Action Input` передай JSON-строку с ключами: feedback_id (ID элемента) и text (текст ответа). Не добавляй лишних кавычек вокруг JSON.
7. После одного ответа заверши работу.

Инструменты:
{tools}

Формат:
Thought: ...
Action: Название одного из инструментов: {tool_names}.
Action Input: ...
Observation: ...

Начинай!

История:
{chat_history}

Команда: {input}
{agent_scratchpad}"""

agent_prompt = PromptTemplate.from_template(agent_prompt_template)
wb_agent_prompt = PromptTemplate.from_template(wb_agent_prompt_template)


STARTUP_TIME = datetime.now()
logging.info(f"[Main] Время запуска зафиксировано: {STARTUP_TIME.isoformat()}")

# --- Управление агентами и памятью ---
agent_store = {}

def get_or_create_agent(user_id: int, is_background_agent=False):
    """Создает или возвращает существующий агент для пользователя."""
    if user_id not in agent_store:
        agent_type = 'фоновых задач' if is_background_agent else f'пользователя {user_id}'
        logging.info(f"[Agent] Создание нового агента для {agent_type}")
        
        # Выбираем промпт в зависимости от типа агента
        prompt = wb_agent_prompt if is_background_agent else agent_prompt
        
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        agent = create_react_agent(llm, all_tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=all_tools,
            memory=memory,
            verbose=True,
            handle_parsing_errors=True
        )
        agent_store[user_id] = agent_executor
    return agent_store[user_id]

# --- Фоновая задача для проверки WB ---
async def background_wb_checker():
    """Периодически проверяет и отвечает на отзывы Wildberries."""
    if not WB_API_KEY:
        return

    logging.info("[BackgroundWB] Запуск фоновой задачи для проверки отзывов Wildberries...")
    agent_executor = get_or_create_agent(user_id=0, is_background_agent=True)

    while True:
        try:
            # ОЧИЩАЕМ ПАМЯТЬ ПЕРЕД КАЖДОЙ ПРОВЕРКОЙ, ЧТОБЫ ИЗБЕЖАТЬ КЭШИРОВАНИЯ РЕШЕНИЙ
            if agent_executor.memory:
                agent_executor.memory.clear()
                logging.info("[BackgroundWB] Память фонового агента очищена перед новой проверкой.")

            logging.info(f"[BackgroundWB] Инициирую проверку всех неотвеченных отзывов и вопросов.")
            await agent_executor.ainvoke({"input": "проверь отзывы и вопросы"})
        except Exception as e:
            logging.error(f"[BackgroundWB] Ошибка в фоновой задаче: {e}", exc_info=True)
        
        await asyncio.sleep(WB_CHECK_INTERVAL_SECONDS)

# --- Управление отложенными задачами и сообщениями ---
user_tasks = {}
user_messages = defaultdict(list)

async def process_user_messages(user_id, event):
    """Задача, которая ждет, объединяет сообщения и отвечает."""
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    
    if user_id not in user_messages:
        return
        
    full_message = " ".join(user_messages.pop(user_id, []))
    logging.info(f"[Telegram] Обработка объединенного сообщения от {user_id}: '{full_message}'")

    try:
        agent_executor = get_or_create_agent(user_id)
        response = await agent_executor.ainvoke({"input": full_message})
        reply = response.get("output", "Извините, я не смог обработать ваш запрос.")
        
        reply = reply.strip().replace("```", "")
        
        await event.reply(reply)
        logging.info(f"[Telegram] Отправлен ответ для {user_id}: '{reply}'")
    except Exception as e:
        logging.error(f"[Telegram] Ошибка при обработке сообщения для {user_id}: {e}", exc_info=True)
        await event.reply("Произошла ошибка. Пожалуйста, попробуйте позже.")
    finally:
        user_tasks.pop(user_id, None)

# --- Обработчик сообщений Telegram ---
@client.on(events.NewMessage(incoming=True, outgoing=False))
async def handler(event):
    """Обрабатывает входящие сообщения с задержкой."""
    sender = await event.get_sender()
    user_id = sender.id
    message_text = event.raw_text
    
    if user_id == 0: # Игнорируем системного агента
        return

    logging.info(f"[Telegram] Получено сообщение от {user_id}: '{message_text}'. Добавлено в очередь.")
    
    user_messages[user_id].append(message_text)
    
    if user_id in user_tasks:
        user_tasks[user_id].cancel()
    
    task = asyncio.create_task(process_user_messages(user_id, event))
    user_tasks[user_id] = task

# --- Запуск приложения ---
async def main():
    """Основная функция для запуска бота и фоновых задач."""
    print("[Main] Запуск Telegram-ассистента...")
    
    # Запускаем фоновую задачу для WB, если есть ключ
    if WB_API_KEY:
        asyncio.create_task(background_wb_checker())
    
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
