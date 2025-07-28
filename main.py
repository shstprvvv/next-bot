import os
import logging
from telethon import TelegramClient, events
from openai import OpenAI
from dotenv import load_dotenv
from langchain.memory import ConversationBufferMemory
from sentence_transformers import SentenceTransformer, util
import json

# Загрузка переменных окружения
load_dotenv()
TELETHON_API_ID = os.getenv('TELETHON_API_ID')
TELETHON_API_HASH = os.getenv('TELETHON_API_HASH')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

client = TelegramClient('user_session', TELETHON_API_ID, TELETHON_API_HASH)
gpt_client = OpenAI(api_key=OPENAI_API_KEY)

# Загрузка FAQ в память
with open('faq.json', encoding='utf-8') as f:
    FAQ = json.load(f)
FAQ_QUESTIONS = [item['question'] for item in FAQ]
FAQ_ANSWERS = [item['answer'] for item in FAQ]

# Модель для эмбеддингов
EMBED_MODEL = SentenceTransformer('paraphrase-MiniLM-L6-v2')
FAQ_EMBEDS = EMBED_MODEL.encode(FAQ_QUESTIONS, convert_to_tensor=True)

# Хранилище памяти по user_id
memory_store = {}

SYSTEM_PROMPT = (
    "Ты — владелец магазина на Wildberries и общаешься с клиентами в переписке. "
    "Отвечай кратко, понятно и дружелюбно, как живой человек. "
    "Используй первый лицo ('я', 'мы'), избегай формального и канцелярского стиля. "
    "Пиши просто, по делу, но с тёплым, человеческим отношением."
)

SUPPORT_PROMPT = (
    "Ты отвечаешь кратко и по делу от лица службы поддержки NEXT. Всегда будь конкретным и профессиональным."
)

FAQ_THRESHOLD = 0.85
FAQ_MATCH_MIN_LEN = 20  # минимальное количество символов во входящем сообщении, чтобы считать FAQ релевантным

def get_memory(user_id):
    if user_id not in memory_store:
        memory_store[user_id] = ConversationBufferMemory(return_messages=True)
    return memory_store[user_id]

def get_faq_or_gpt_answer(question: str) -> str:
    # 1. Поиск похожего вопроса в FAQ
    q_emb = EMBED_MODEL.encode(question, convert_to_tensor=True)
    cos_scores = util.pytorch_cos_sim(q_emb, FAQ_EMBEDS)[0]
    best_idx = int(cos_scores.argmax())
    best_score = float(cos_scores[best_idx])
    if best_score >= 0.7:
        return FAQ_ANSWERS[best_idx]
    # 2. Если не найдено — запрос к GPT
    response = gpt_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SUPPORT_PROMPT},
            {"role": "user", "content": question}
        ],
        max_tokens=80,
        temperature=0.5,
    )
    return response.choices[0].message.content.strip()

def generate_support_reply(user_id, message_text):
    memory = get_memory(user_id)
    # Добавляем новое сообщение пользователя в память
    memory.chat_memory.add_user_message(message_text)
    # Формируем историю для GPT
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    for msg in memory.chat_memory.messages:
        if msg.type == 'human':
            messages.append({"role": "user", "content": msg.content})
        else:
            messages.append({"role": "assistant", "content": msg.content})
    response = gpt_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=80,
        temperature=0.5,
    )
    reply = response.choices[0].message.content.strip()
    # Добавляем ответ ассистента в память
    memory.chat_memory.add_ai_message(reply)
    return reply

@client.on(events.NewMessage(incoming=True, outgoing=False))
async def handler(event):
    sender = await event.get_sender()
    user_id = sender.id
    sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', 'Unknown')
    message_text = event.raw_text
    logging.info(f"Получено сообщение от {sender_name}: {message_text}")
    try:
        memory = get_memory(user_id)
        # Добавляем сообщение пользователя в память
        memory.chat_memory.add_user_message(message_text)
        # Пробуем найти ответ в FAQ
        q_emb = EMBED_MODEL.encode(message_text, convert_to_tensor=True)
        cos_scores = util.pytorch_cos_sim(q_emb, FAQ_EMBEDS)[0]
        best_idx = int(cos_scores.argmax())
        best_score = float(cos_scores[best_idx])
        if best_score >= FAQ_THRESHOLD and len(message_text) >= FAQ_MATCH_MIN_LEN:
            reply = FAQ_ANSWERS[best_idx]
            # Добавляем ответ из FAQ в память
            memory.chat_memory.add_ai_message(reply)
        else:
            # Формируем историю для GPT
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
            ]
            for msg in memory.chat_memory.messages:
                if msg.type == 'human':
                    messages.append({"role": "user", "content": msg.content})
                else:
                    messages.append({"role": "assistant", "content": msg.content})
            response = gpt_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=80,
                temperature=0.5,
            )
            reply = response.choices[0].message.content.strip()
            memory.chat_memory.add_ai_message(reply)
        await event.reply(reply)
        logging.info(f"Отправлен ответ: {reply}")
    except Exception as e:
        logging.error(f"Ошибка при генерации или отправке ответа: {e}")

if __name__ == "__main__":
    print("Запуск... Если вы впервые запускаете скрипт, потребуется авторизация через Telegram.")
    with client:
        client.run_until_disconnected() 