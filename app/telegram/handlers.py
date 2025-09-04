import asyncio
import logging
from collections import defaultdict
from telethon import events

# Множество для хранения ID чатов, которые находятся под ручным управлением оператора
OPERATOR_CONTROLLED_CHATS = set()


def setup_telegram_handlers(client, message_delay_seconds: int, get_or_create_chain, normalize_reply=None):
    """
    Регистрирует универсальный обработчик сообщений Telegram.
    """
    user_tasks = {}
    user_messages = defaultdict(list)

    # Получаем специальный логгер для неотвеченных вопросов
    unanswered_logger = logging.getLogger('unanswered')
    fallback_phrase = "К сожалению, у меня нет готового решения"

    async def process_user_messages(user_id, event):
        await asyncio.sleep(message_delay_seconds)

        if user_id not in user_messages:
            return

        full_message = " ".join(user_messages.pop(user_id, []))
        logging.info(f"[Telegram] Обработка объединенного сообщения от {user_id}: '{full_message}'")

        try:
            chain = get_or_create_chain(user_id)
            response = await chain.ainvoke({"question": full_message})
            raw_reply = response.get("answer", "")
            if callable(normalize_reply):
                reply = normalize_reply(raw_reply)
            else:
                reply = (raw_reply or "").strip().replace("```", "") or "Извините, я не смог обработать ваш запрос."

            # Проверяем, был ли ответ "заглушкой"
            if fallback_phrase in reply:
                unanswered_logger.info(f"[Telegram] UserID: {user_id}, Question: '{full_message}'")

            await event.reply(reply)
            logging.info(f"[Telegram] Отправлен ответ для {user_id}: '{reply}'")
        except Exception as e:
            logging.error(f"[Telegram] Ошибка при обработке сообщения для {user_id}: {e}", exc_info=True)
            await event.reply("Произошла ошибка. Пожалуйста, попробуйте позже.")
        finally:
            user_tasks.pop(user_id, None)

    @client.on(events.NewMessage())
    async def universal_handler(event):
        # --- Блок управления для оператора (исходящие сообщения) ---
        if event.out:
            # Убедимся, что это личный чат с пользователем
            if not event.is_private:
                return

            chat_id = event.chat_id
            command = event.raw_text.strip()

            # Команда для перехвата управления
            if command == '/takeover':
                if chat_id not in OPERATOR_CONTROLLED_CHATS:
                    OPERATOR_CONTROLLED_CHATS.add(chat_id)
                    logging.info(f"[Operator] Управление чатом {chat_id} перехвачено.")
                await event.delete()
                return

            # Команда для возврата управления боту
            if command == '/bot':
                if chat_id in OPERATOR_CONTROLLED_CHATS:
                    OPERATOR_CONTROLLED_CHATS.remove(chat_id)
                    logging.info(f"[Operator] Управление чатом {chat_id} возвращено боту.")
                await event.delete()
                return
            
            # Обычные исходящие сообщения оператора просто уходят, бот на них не реагирует
            return

        # --- Блок обработки входящих сообщений от пользователей ---
        if event.is_private: # Реагируем только на сообщения в личных чатах
            user_id = event.sender_id

            # Проверяем, не находится ли чат на ручном управлении
            if user_id in OPERATOR_CONTROLLED_CHATS:
                logging.info(f"[Operator] Сообщение от {user_id} проигнорировано (ручное управление).")
                return

            # --- Стандартная логика обработки сообщения ботом ---
            message_text = event.raw_text
            logging.info(f"[Telegram] Получено сообщение от {user_id}: '{message_text}'. Добавлено в очередь.")

            user_messages[user_id].append(message_text)

            if user_id in user_tasks:
                user_tasks[user_id].cancel()

            task = asyncio.create_task(process_user_messages(user_id, event))
            user_tasks[user_id] = task

    return {
        "universal_handler": universal_handler,
    }


