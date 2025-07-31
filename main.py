import os
import logging
import asyncio
from collections import defaultdict
from telethon import TelegramClient, events
from dotenv import load_dotenv
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from tools import create_knowledge_base_tool # Импортируем функцию

# --- Конфигурация ---
load_dotenv()
TELETHON_API_ID = os.getenv('TELETHON_API_ID')
TELETHON_API_HASH = os.getenv('TELETHON_API_HASH')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE')
MESSAGE_DELAY_SECONDS = 30 # Время ожидания перед ответом

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)

# --- Инициализация клиентов и моделей ---
client = TelegramClient('user_session', TELETHON_API_ID, TELETHON_API_HASH)
llm = ChatOpenAI(
    model_name="gpt-4o-mini",
    temperature=0.2,
    openai_api_key=OPENAI_API_KEY,
    base_url=OPENAI_API_BASE
)

# Создаем RAG-инструмент, передавая ему ключ и URL
knowledge_base_tool = create_knowledge_base_tool(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
if knowledge_base_tool is None:
    logging.error("Не удалось создать инструмент базы знаний. Приложение не может продолжить работу.")
    exit() # Выходим, если инструмент не создался

tools = [knowledge_base_tool]

# --- Системный промпт для агента ---
agent_prompt_template = """
### Роль и Стиль
Ты — официальный онлайн-консультант техподдержки ТВ-приставок бренда NEXT.
Твоя главная задача — помочь пользователю. Отвечай всегда вежливо, кратко, информативно и дружелюбно. Объясняй простым языком, без сложных терминов.

### Инструкция по работе
1.  Для ответа на ЛЮБОЙ вопрос о продукте, его функциях или проблемах, **ты ОБЯЗАН сначала использовать инструмент `KnowledgeBaseSearch`**.
2.  Получив информацию из инструмента, **сформулируй на её основе свой собственный, уникальный ответ**. Не копируй текст из результатов поиска дословно.
3.  Если инструмент не нашел релевантной информации, вежливо сообщи, что у тебя нет данных по этому вопросу.
4.  Если после всех предложенных решений проблема пользователя не решается, или если она явно указывает на аппаратный дефект (например, приставка не включается), всегда предлагай оформить возврат через маркетплейс, где была совершена покупка (Wildberries или Ozon).

### Инструменты
У тебя есть доступ к следующим инструментам:
{tools}

Чтобы использовать инструмент, используй следующий формат:
```
Thought: Мне нужно найти информацию по вопросу пользователя. Я использую KnowledgeBaseSearch.
Action: {tool_names}
Action Input: Вопрос пользователя как есть.
Observation: Результат поиска в базе знаний.
```

Когда у тебя есть финальный ответ, используй формат:
```
Thought: Я нашел всю необходимую информацию и готов дать ответ.
Final Answer: Финальный ответ для пользователя, сгенерированный на основе полученных данных и в соответствии со стилем общения.
```

Начинай!

История переписки:
{chat_history}

Новый вопрос от пользователя: {input}
{agent_scratchpad}
"""
agent_prompt = PromptTemplate.from_template(agent_prompt_template)

# --- Управление агентами и памятью ---
agent_store = {}

def get_or_create_agent(user_id: int):
    """Создает или возвращает существующий агент для пользователя."""
    if user_id not in agent_store:
        logging.info(f"Создание нового агента для пользователя {user_id}")
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        agent = create_react_agent(llm, tools, agent_prompt)
        agent_executor = AgentExecutor(
            agent=agent, 
            tools=tools, 
            memory=memory, 
            verbose=True,
            handle_parsing_errors=True # Добавляем обработчик ошибок парсинга
        )
        agent_store[user_id] = agent_executor
    return agent_store[user_id]

# --- Управление отложенными задачами и сообщениями ---
user_tasks = {}
user_messages = defaultdict(list)

async def process_user_messages(user_id, event):
    """Задача, которая ждет, объединяет сообщения и отвечает."""
    await asyncio.sleep(MESSAGE_DELAY_SECONDS)
    
    if user_id not in user_messages:
        return # Сообщения были очищены, задача отменена
        
    full_message = " ".join(user_messages.pop(user_id, []))
    logging.info(f"Обработка объединенного сообщения от {user_id}: '{full_message}'")

    try:
        agent_executor = get_or_create_agent(user_id)
        response = await agent_executor.ainvoke({"input": full_message})
        reply = response.get("output", "Извините, я не смог обработать ваш запрос.")
        
        reply = reply.strip().replace("```", "")
        
        await event.reply(reply)
        logging.info(f"Отправлен ответ для {user_id}: '{reply}'")
    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения для {user_id}: {e}", exc_info=True)
        await event.reply("Произошла ошибка. Пожалуйста, попробуйте позже.")
    finally:
        # Убираем задачу из хранилища после выполнения
        user_tasks.pop(user_id, None)

# --- Обработчик сообщений Telegram ---
@client.on(events.NewMessage(incoming=True, outgoing=False))
async def handler(event):
    """Обрабатывает входящие сообщения с задержкой."""
    sender = await event.get_sender()
    user_id = sender.id
    message_text = event.raw_text
    
    logging.info(f"Получено сообщение от {user_id}: '{message_text}'. Добавлено в очередь.")
    
    # Добавляем сообщение в "пачку"
    user_messages[user_id].append(message_text)
    
    # Если для этого пользователя уже есть таймер, отменяем его
    if user_id in user_tasks:
        user_tasks[user_id].cancel()
    
    # Запускаем новый таймер (новую задачу)
    task = asyncio.create_task(process_user_messages(user_id, event))
    user_tasks[user_id] = task

# --- Запуск приложения ---
if __name__ == "__main__":
    print("Запуск Telegram-ассистента...")
    with client:
        client.run_until_disconnected() 