import asyncio
import logging
from collections import defaultdict
from telethon import events, TelegramClient
from app.core.use_cases.answer_question import AnswerQuestionUseCase

logger = logging.getLogger(__name__)

class TelegramAdapter:
    def __init__(self, client: TelegramClient, use_case: AnswerQuestionUseCase, message_delay: int = 2):
        self.client = client
        self.use_case = use_case
        self.message_delay = message_delay
        
        self.user_messages = defaultdict(list)
        self.user_tasks = {}
        self.operator_mode_chats = set() # Чаты, где управление перехвачено оператором
        
        # Регистрация хендлеров
        self.client.add_event_handler(self.handle_incoming_message, events.NewMessage())

    async def handle_incoming_message(self, event):
        chat_id = event.chat_id
        text = event.raw_text.strip()

        # 1. Обработка команд оператора (исходящие сообщения от меня или входящие команды)
        # Если сообщение исходящее (event.out) и это команда
        if event.out:
            if text == '/takeover':
                self.operator_mode_chats.add(chat_id)
                logger.info(f"[Operator] Управление чатом {chat_id} перехвачено.")
                await event.delete()
                return
            elif text == '/bot':
                if chat_id in self.operator_mode_chats:
                    self.operator_mode_chats.remove(chat_id)
                    logger.info(f"[Operator] Управление чатом {chat_id} возвращено боту.")
                await event.delete()
                return
            # Остальные исходящие игнорируем
            return

        # 2. Обработка входящих сообщений от пользователей
        if not event.is_private:
            return

        # Если чат в режиме оператора - игнорируем (бот молчит)
        if chat_id in self.operator_mode_chats:
            logger.info(f"[Operator] Сообщение от {chat_id} пропущено (ручной режим).")
            return

        # 3. Стандартная логика бота
        logger.info(f"[Telegram] Сообщение от {chat_id}: '{text}'")

        # Логика склеивания сообщений (debounce)
        self.user_messages[chat_id].append(text)
        
        if chat_id in self.user_tasks:
            self.user_tasks[chat_id].cancel()
            
        self.user_tasks[chat_id] = asyncio.create_task(self.process_messages(chat_id, event))

    async def process_messages(self, user_id, event):
        await asyncio.sleep(self.message_delay)
        
        if user_id not in self.user_messages:
            return
            
        full_message = " ".join(self.user_messages.pop(user_id))
        logger.info(f"[Telegram] Обработка для {user_id}: '{full_message}'")
        
        # Здесь мы можем доставать историю диалога из базы (пока заглушка)
        history = [] 
        
        # Вызов Use Case
        try:
            # Уведомляем Telegram, что "печатаем" (опционально)
            async with self.client.action(user_id, 'typing'):
                answer = await self.use_case.execute(user_id, full_message, history)
            
            await event.reply(answer)
            logger.info(f"[Telegram] Ответ отправлен {user_id}")
            
        except Exception as e:
            logger.error(f"[Telegram] Ошибка обработки: {e}", exc_info=True)
            await event.reply("Произошла ошибка при обработке вашего запроса.")
        finally:
            self.user_tasks.pop(user_id, None)
