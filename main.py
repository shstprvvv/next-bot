import os
import logging
import asyncio
from collections import defaultdict, deque
from datetime import datetime
from telethon import TelegramClient, events
from dotenv import load_dotenv
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from tools import create_knowledge_base_tool, get_unanswered_feedbacks_tool, post_feedback_answer_tool
import json

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
WB_CHECK_INTERVAL_SECONDS = 300
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

ВАЖНО: Названия инструментов должны быть ТОЧНО такими, как в списке ({tool_names}), без точек, кавычек и других знаков.

Тебе в {input} будет передан JSON с одним вопросом или отзывом. Твоя задача — ответить на него.

Порядок действий:
1. Используй инструмент `KnowledgeBaseSearch` с текстом из JSON, чтобы найти информацию для ответа.
2. Сгенерируй вежливый и полезный ответ. Используй эмодзи.
3. Используй инструмент `PostFeedbackAnswer`, чтобы отправить сгенерированный ответ.

Начинай!

Инструменты:
{tools}

Формат:
Thought: ...
Action: Название одного из инструментов: {tool_names}.
Action Input: ...
Observation: ...

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

    # Используем deque для хранения ID последних 100 обработанных элементов,
    # чтобы избежать повторных ответов из-за задержки API WB.
    recently_answered_ids = deque(maxlen=100)
    
    # Получаем инстанс инструмента для прямого вызова
    unanswered_tool = get_unanswered_feedbacks_tool()

    while True:
        try:
            if agent_executor.memory:
                agent_executor.memory.clear()
                logging.info("[BackgroundWB] Память фонового агента очищена перед новой проверкой.")

            logging.info("[BackgroundWB] Получение списка неотвеченных элементов...")
            # Прямой вызов инструмента для получения списка
            items_json = unanswered_tool.func("")
            
            try:
                items = json.loads(items_json)
            except (json.JSONDecodeError, TypeError):
                items = []

            if not items:
                logging.info("[BackgroundWB] Новых неотвеченных элементов нет.")
            else:
                logging.info(f"[BackgroundWB] Получено {len(items)} элементов. Поиск нового для ответа...")
                
                # Ищем первый элемент, на который мы еще не отвечали в этой сессии
                item_to_answer = None
                for item in items:
                    if item.get("id") not in recently_answered_ids:
                        item_to_answer = item
                        break
                
                if item_to_answer:
                    item_id = item_to_answer.get("id")
                    logging.info(f"[BackgroundWB] Найден новый элемент для ответа. ID: {item_id}")
                    
                    # Формируем конкретный запрос для агента, чтобы он ответил на этот элемент
                    input_prompt = (
                        f"Ответь на следующий отзыв/вопрос с ID {item_id}. "
                        f"Вот его содержимое в формате JSON: {json.dumps(item_to_answer, ensure_ascii=False)}"
                    )
                    
                    response = await agent_executor.ainvoke({"input": input_prompt})
                    
                    # Если ответ был успешным, добавляем ID в кэш
                    if response and response.get("output") and "не удалось" not in response.get("output").lower():
                        logging.info(f"[BackgroundWB] Ответ на ID {item_id} считается успешным. Добавляю в кэш недавно отвеченных.")
                        recently_answered_ids.append(item_id)
                    else:
                        logging.warning(f"[BackgroundWB] Попытка ответа на ID {item_id} могла быть неуспешной. Ответ агента: {response.get('output')}")
                        
                else:
                    logging.info("[BackgroundWB] Все полученные элементы уже были недавно обработаны. Пропускаем цикл.")

        except Exception as e:
            logging.error(f"[BackgroundWB] Ошибка в фоновой задаче: {e}", exc_info=True)
        
        logging.info(f"[BackgroundWB] Следующая проверка через {WB_CHECK_INTERVAL_SECONDS} секунд.")
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
