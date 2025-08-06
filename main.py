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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    wb_tools.extend([get_unanswered_feedbacks_tool(lambda: STARTUP_TIME), post_feedback_answer_tool()])
    logging.info("[Main] Инструменты для Wildberries успешно инициализированы.")
else:
    logging.warning("[Main] Ключ WB_API_KEY не найден. Функционал Wildberries будет отключен.")

all_tools = [knowledge_base_tool] + wb_tools

# --- Системный промпт для агента ---
# Общий промпт для ответов в Telegram
agent_prompt_template = """
### Роль и Стиль
Ты — официальный онлайн-консультант техподдердки ТВ-приставок бренда NEXT.
Твоя главная задача — помочь пользователю.
Отвечай всегда вежливо, кратко, информативно и дружелюбно. Объясняй простым языком, без сложных терминов.
При первом ответе поздоровайся («Здравствуйте!») и кратко представься. В дальнейшем диалоге повторное приветствие не требуется.

### Инструкции по работе
1.  **Особый случай: приветствие.** Если сообщение пользователя — это простое приветствие (например, "Привет", "Добрый день") и не содержит вопроса, ты **НЕ ДОЛЖЕН** использовать инструменты. Твоя задача — просто поздороваться в ответ и предложить помощь.
    Пример твоих действий в этом случае:
    ```
    Thought: The user is just greeting me. I will greet them back and ask how I can help, without using any tools.
    Final Answer: Здравствуйте! Я — официальный онлайн-консультант бренда NEXT. Чем я могу вам помочь?
    ```
2.  **Вопросы о продукте.** Для ответа на ЛЮБОЙ содержательный вопрос о продукте, его функциях или проблемах, **ты ОБЯЗАН сначала использовать инструмент `KnowledgeBaseSearch`**.
3.  **Формулировка ответа.** Получив информацию из инструмента, **сформулируй на её основе свой собственный, уникальный ответ**. Не копируй текст из результатов поиска дословно.
4.  **Если ничего не найдено.** Если инструмент не нашел релевантной информации, вежливо сообщи, что уточняешь вопрос у коллег, или попроси у пользователя дополнительные детали и предложи базовые шаги (перезагрузка, проверка интернета).
5.  **Аппаратный дефект.** Если после всех предложенных решений проблема пользователя не решается, или если она явно указывает на аппаратный дефект (например, приставка не включается), всегда предлагай оформить возврат через маркетплейс, где была совершена покупка.

### Инструменты
У тебя есть доступ к следующим инструментам:
{tools}

Чтобы использовать инструмент, используй следующий формат:
```
Thought: Твои мысли о том, что делать дальше.
Action: Название одного из инструментов: {tool_names}
Action Input: Входные данные для инструмента.
Observation: Результат выполнения инструмента.
```

Когда у тебя есть финальный ответ, используй формат:
```
Thought: Я нашел всю необходимую информацию и готов дать ответ.
Final Answer: Финальный ответ для пользователя.
```

Начинай!

История переписки:
{chat_history}

Новый вопрос от пользователя: {input}
{agent_scratchpad}
"""

# Специализированный промпт для ответов на отзывы в Wildberries
wb_agent_prompt_template = """
### Роль и Стиль
Ты — маркетолог и официальный представитель бренда NEXT. Твоя цель — не просто ответить на отзыв, а превратить его в **инструмент продаж**. Каждый твой комментарий должен укреплять положительный имидж бренда, подчеркивать ценность продукта и мотивировать на настоящие и будущие покупки. Тон — экспертный, дружелюбный и убедительный.

### Инструкции по работе
Твоя задача — обработать ОДИН отзыв за раз.

1.  Используй инструмент `GetUnansweredFeedbacks`, чтобы получить список неотвеченных отзывов. Инструмент вернет JSON-список.
2.  **Проанализируй результат:**
    *   Если инструмент `GetUnansweredFeedbacks` вернул пустой список (`[]`), это означает, что новых отзывов нет. Твоя работа на этом закончена. Ты **ДОЛЖЕН** немедленно использовать `Final Answer`, например: `Final Answer: Новых отзывов для обработки нет.`
    *   Если в списке есть отзывы, возьми **ТОЛЬКО ПЕРВЫЙ** отзыв для обработки.
3.  **Если отзыв есть:**
    a. Внимательно прочти его текст, оценку, плюсы и минусы из JSON-объекта.
    b. Используй `KnowledgeBaseSearch` с текстом отзыва в качестве запроса, чтобы найти технические детали или стандартные решения проблемы.
    c. Сформулируй ответ, следуя правилам ниже.
    d. Используй инструмент `PostFeedbackAnswer`, передав ему `feedback_id` из данных отзыва и сгенерированный текст ответа.
    e. После отправки одного ответа, твоя работа на этом закончена. **Не пытайся обработать второй отзыв из списка.**

### Правила формирования "продающего" ответа для Wildberries:
1.  **Начинай с благодарности.** Всегда благодари пользователя за уделенное время и отзыв, например: "Здравствуйте! Благодарим вас за отзыв и обратную связь 🙏."
2.  **Реакция на оценку:**
    *   **Положительный отзыв (4-5 звезд):** Не просто благодари, а **усиливай позитив**. Кратко упомяни ключевую особенность, которую затронул клиент. Пример: "Рады, что вы оценили скорость работы! Мы вложили много сил в оптимизацию процессора для плавной картинки в 4K."
    *   **Негативный отзыв (1-3 звезды):**
        *   Вырази сожаление о возникшей проблеме. Пример: "Нам очень жаль, что вы столкнулись с такой ситуацией."
        *   **Обязательно добавь фразу о качестве.** Пример: "Хотим заверить, что мы тщательно следим за качеством нашей продукции, и подавляющее большинство покупателей (более 1000 положительных отзывов) остаются довольны работой приставки."
        *   **Обязательно упомяни гарантию.** Пример: "Напоминаем, что на все наши устройства действует гарантия в течение года."
3.  **Ответ по существу (Продающий подход):**
    *   Если проблема решаема (на основе `KnowledgeBaseSearch`), предложи решение, подчеркнув, как оно раскрывает **ценность продукта**. Пример: "Попробуйте, пожалуйста, переключить режим HDR в настройках, это раскроет весь потенциал цветопередачи вашего телевизора!"
    *   Если это брак, представь возврат не как проблему, а как **часть нашего премиального сервиса и гарантийных обязательств**. Пример: "Мы ценим ваше время, поэтому для быстрой замены просто оформите возврат на маркетплейсе. Наша годовая гарантия — это ваша уверенность в покупке."
4.  **Используй эмодзи.** Добавляй 1-2 уместных эмоdзи в ответ, чтобы сделать его более живым, но не переусердствуй.
5.  **Завершение (Призыв к лояльности):** Заверши ответ фразой, мотивирующей на лояльность. Пример: "Спасибо, что помогаете нам становиться лучше! Уверены, вы еще оцените все возможности наших устройств. Хорошего дня! 😊 С уважением, команда бренда NEXT."

### Инструменты
У тебя есть доступ к следующим инструментам:
{tools}

Чтобы использовать инструмент, используй следующий формат:
```
Thought: Твои мысли о том, что делать дальше.
Action: Название одного из инструментов: {tool_names}
Action Input: Входные данные для инструмента.
Observation: Результат выполнения инструмента.
```

Когда у тебя есть финальный ответ для отправки на Wildberries, используй формат:
```
Thought: Я сгенерировал ответ на отзыв и готов его отправить.
Action: PostFeedbackAnswer
Action Input: {{"feedback_id": "ID_ОТЗЫВА", "text": "ТЕКСТ_ОТВЕТА"}}
```

Если нужно просто завершить работу (например, нет новых отзывов), используй `Final Answer`.

Начинай!

История предыдущих действий (для контекста):
{chat_history}

Команда: {input}
{agent_scratchpad}
"""

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
            logging.info(f"[BackgroundWB] Инициирую проверку отзывов (только новые с {STARTUP_TIME.isoformat()}).")
            await agent_executor.ainvoke({"input": "проверь отзывы"})
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
