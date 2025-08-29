import asyncio
import logging
from collections import defaultdict
from telethon import events


def setup_telegram_handlers(client, message_delay_seconds: int, get_or_create_chain, normalize_reply=None):
    """
    Регистрирует обработчики сообщений Telegram на переданном клиенте.

    - message_delay_seconds: задержка для объединения сообщений от одного пользователя
    - get_or_create_chain: callable(user_id) -> ConversationalRetrievalChain
    """

    user_tasks = {}
    user_messages = defaultdict(list)

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

            await event.reply(reply)
            logging.info(f"[Telegram] Отправлен ответ для {user_id}: '{reply}'")
        except Exception as e:
            logging.error(f"[Telegram] Ошибка при обработке сообщения для {user_id}: {e}", exc_info=True)
            await event.reply("Произошла ошибка. Пожалуйста, попробуйте позже.")
        finally:
            user_tasks.pop(user_id, None)

    @client.on(events.NewMessage(incoming=True, outgoing=False))
    async def handler(event):
        sender = await event.get_sender()
        user_id = sender.id
        message_text = event.raw_text

        if user_id == 0:  # Игнорируем системного агента
            return

        logging.info(f"[Telegram] Получено сообщение от {user_id}: '{message_text}'. Добавлено в очередь.")

        user_messages[user_id].append(message_text)

        if user_id in user_tasks:
            user_tasks[user_id].cancel()

        task = asyncio.create_task(process_user_messages(user_id, event))
        user_tasks[user_id] = task

    # возвращаем ссылки (на случай тестов/очистки), но это опционально
    return {
        "process_user_messages": process_user_messages,
        "handler": handler,
    }


