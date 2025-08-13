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
from tools import (
    create_knowledge_base_tool,
    get_unanswered_feedbacks_tool,
    post_feedback_answer_tool,
    get_chat_events_tool,
    post_chat_message_tool,
    is_knowledge_base_ready,
)
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
WB_CHAT_POLL_INTERVAL_SECONDS = 20
WB_CHAT_DEBUG = os.getenv('WB_CHAT_DEBUG', '0') == '1'
DISABLE_SENDING_IF_KB_UNAVAILABLE = os.getenv('DISABLE_SENDING_IF_KB_UNAVAILABLE', '1') == '1'
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
    wb_tools.extend([
        get_unanswered_feedbacks_tool(),
        post_feedback_answer_tool(),
        get_chat_events_tool(),
        post_chat_message_tool(),
    ])
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
Action: Название одного из инструментов: {tool_names}
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

# --- Фоновая задача для проверки WB (отзывы/вопросы) ---
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
                    
                    # Если база знаний недоступна и политика запрещает отправку — пропускаем
                    if DISABLE_SENDING_IF_KB_UNAVAILABLE and not is_knowledge_base_ready():
                        logging.warning(f"[BackgroundWB] KB недоступна. Пропускаю отправку ответа для {item_id}.")
                        recently_answered_ids.append(item_id)
                        continue

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


# --- Фоновая задача для чатов WB ---
async def background_wb_chat_responder():
    """Периодически опрашивает события чатов и автоматически отвечает."""
    if not WB_API_KEY:
        return

    logging.info("[BackgroundWBChat] Запуск фоновой задачи для чатов WB...")
    agent_executor = get_or_create_agent(user_id=-1, is_background_agent=True)

    last_event_id = None
    next_token = None
    reply_sign_cache = {}
    get_events_tool = get_chat_events_tool()
    send_tool = post_chat_message_tool()

    while True:
        try:
            if agent_executor.memory:
                agent_executor.memory.clear()
            payload = {}
            if next_token is not None:
                payload["next"] = next_token
            elif last_event_id is not None:
                payload["last_event_id"] = last_event_id
            events_json = get_events_tool.func(json.dumps(payload))
            if WB_CHAT_DEBUG:
                logging.info(f"[BackgroundWBChat] Raw events response: {events_json}")
            try:
                events = json.loads(events_json) if isinstance(events_json, str) else events_json
            except Exception:
                events = None

            if not events or not isinstance(events, dict):
                if WB_CHAT_DEBUG:
                    logging.info("[BackgroundWBChat] Нет событий или неожиданный формат ответа")
                await asyncio.sleep(WB_CHAT_POLL_INTERVAL_SECONDS)
                continue

            # Ожидаем структуру вида {"data": {"events": [...]}}
            # Структура по логу: {"result": {"next": <int>, "events": [...]}}
            container = None
            if isinstance(events, dict):
                container = events.get("result") or events.get("data") or {}
            next_token = container.get("next") if isinstance(container, dict) else None
            event_list = (container or {}).get("events", []) if isinstance(container, dict) else []

            logging.info(f"[BackgroundWBChat] Получено событий: {len(event_list)}")
            for ev in event_list:
                # Запоминаем максимальный id
                ev_id = ev.get("id") or ev.get("eventId") or ev.get("eventID")
                if isinstance(ev_id, int):
                    last_event_id = max(last_event_id or 0, ev_id)

                # Нас интересуют входящие сообщения от покупателя
                # Тип события и структура зависят от WB, но обычно есть chatId и message/text
                ev_type = ev.get("type") or ev.get("eventType") or ev.get("event_type")
                if str(ev_type).lower() not in ("message", "msg", "user_message", "buyer_message"):
                    if WB_CHAT_DEBUG:
                        logging.info(f"[BackgroundWBChat] Пропущено событие типа {ev_type}")
                    continue

                payload_message = ev.get("message") or {}
                chat_id = (
                    ev.get("chatId") or ev.get("chatID") or
                    payload_message.get("chatId") or payload_message.get("chatID") or
                    payload_message.get("chat_id")
                )
                text = payload_message.get("text") or ev.get("text")
                reply_sign = payload_message.get("replySign")
                sender = (ev.get("sender") or payload_message.get("sender") or "").lower()

                # Кэшируем replySign на чат, если пришёл
                if chat_id and reply_sign:
                    reply_sign_cache[str(chat_id)] = reply_sign

                # Отвечаем только на сообщения клиента
                if sender and sender != "client":
                    if WB_CHAT_DEBUG:
                        logging.info("[BackgroundWBChat] Пропуск: отправитель не клиент")
                    continue

                if not chat_id or not text:
                    if WB_CHAT_DEBUG:
                        logging.info("[BackgroundWBChat] Нет chat_id или текста в событии")
                    continue

                # Сформировать подсказку агенту для генерации ответа
                input_prompt = (
                    f"Сгенерируй вежливый ответ на сообщение покупателя в WB чате.\n"
                    f"Сообщение: {text}"
                )
                try:
                    response = await agent_executor.ainvoke({"input": input_prompt})
                    reply = (response or {}).get("output", "")
                    if reply:
                        reply = reply.strip().replace("```", "")
                        if WB_CHAT_DEBUG:
                            logging.info(f"[BackgroundWBChat] Ответ (preview): {reply[:160]}…")
                        final_reply_sign = reply_sign or reply_sign_cache.get(str(chat_id))
                        if not final_reply_sign and WB_CHAT_DEBUG:
                            logging.info("[BackgroundWBChat] Нет replySign — пропускаю отправку для безопасности")
                            continue
                        send_result = send_tool.func(json.dumps({
                            "chat_id": str(chat_id),
                            "text": reply,
                            "reply_sign": final_reply_sign
                        }))
                        if isinstance(send_result, str) and send_result.startswith("Сообщение отправлено"):
                            logging.info(f"[BackgroundWBChat] Ответ отправлен в чат {chat_id}")
                        else:
                            logging.warning(f"[BackgroundWBChat] Отправка могла не пройти: {send_result}")
                except Exception as e:
                    logging.error(f"[BackgroundWBChat] Ошибка генерации/отправки ответа: {e}", exc_info=True)

        except Exception as e:
            logging.error(f"[BackgroundWBChat] Ошибка в воркере: {e}", exc_info=True)

        await asyncio.sleep(WB_CHAT_POLL_INTERVAL_SECONDS)

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
        # Если KB недоступна и политика запрещает отправку — ответ не отправляем
        if DISABLE_SENDING_IF_KB_UNAVAILABLE and not is_knowledge_base_ready():
            logging.warning("[Telegram] KB недоступна. Ответ не отправляется по политике DISABLE_SENDING_IF_KB_UNAVAILABLE.")
            await event.reply("Извините, сейчас сервис временно недоступен. Пожалуйста, попробуйте позже.")
            return
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
        asyncio.create_task(background_wb_chat_responder())
    
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
