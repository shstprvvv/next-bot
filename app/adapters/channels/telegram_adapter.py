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
        self.chat_history = defaultdict(list) # Храним историю диалогов (в памяти)
        
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

        # Отслеживаем попытки (чтобы предложить возврат, если тупим)
        if not hasattr(self, 'user_attempts'):
            self.user_attempts = defaultdict(int)

        # 3. Стандартная логика бота
        logger.info(f"[Telegram] Сообщение от {chat_id}: '{text}'")

        # Логика склеивания сообщений (debounce)
        self.user_messages[chat_id].append(text)
        
        if chat_id in self.user_tasks:
            self.user_tasks[chat_id].cancel()
            
        self.user_tasks[chat_id] = asyncio.create_task(self.process_messages(chat_id, event))

    async def process_messages(self, user_id, event):
        try:
            await asyncio.sleep(self.message_delay)
        except asyncio.CancelledError:
            # Нормально: пришло новое сообщение, старую задачу отменили (debounce)
            return
        
        if user_id not in self.user_messages:
            return
            
        full_message = " ".join(self.user_messages.pop(user_id))
        logger.info(f"[Telegram] Обработка для {user_id}: '{full_message}'")
        
        # Здесь мы достаем историю диалога из памяти (пока в ОЗУ)
        history = self.chat_history[user_id].copy()
        
        # Увеличиваем счетчик сообщений для отслеживания "тупняков"
        self.user_attempts[user_id] += 1
        
        # Вызов Use Case
        try:
            # Уведомляем Telegram, что "печатаем" (опционально)
            async with self.client.action(user_id, 'typing'):
                answer = await self.use_case.execute(user_id, full_message, history, source="telegram")
            
            # Если бот уже долго не может решить проблему (больше 4 сообщений) и отвечает отмазками
            if self.user_attempts[user_id] >= 4 and ("нет готового решения" in answer or "к сожалению" in answer.lower()):
                answer = (
                    "К сожалению, я уже несколько раз попытался найти решение, но дистанционно помочь не получается. 😔\n\n"
                    "Похоже, что ваша приставка или пульт имеет заводской брак или техническую неисправность.\n"
                    "Напоминаю, что на товар действует гарантия 1 год! Вы можете легко вернуть приставку через личный кабинет Wildberries:\n"
                    "1. Зайдите в покупки.\n"
                    "2. Выберите приставку и нажмите «Оформить возврат».\n"
                    "3. Обязательно укажите причину «Брак» и приложите видео неисправности.\n\n"
                    "Мы без проблем одобрим возврат, и вы получите деньги обратно."
                )
                self.user_attempts[user_id] = 0 # Сбрасываем счетчик после предложения возврата

            await event.reply(answer)
            logger.info(f"[Telegram] Ответ отправлен {user_id}")
            
            # Сохраняем в историю текущий шаг
            self.chat_history[user_id].append(f"Клиент: {full_message}")
            self.chat_history[user_id].append(f"Бот: {answer}")
            
            # Ограничиваем историю в памяти (например, храним только 20 последних сообщений)
            if len(self.chat_history[user_id]) > 20:
                self.chat_history[user_id] = self.chat_history[user_id][-20:]
            
        except Exception as e:
            logger.error(f"[Telegram] Ошибка обработки: {e}", exc_info=True)
            try:
                await event.reply("Произошла ошибка при обработке вашего запроса.")
            except Exception:
                logger.warning("[Telegram] Не удалось отправить сообщение об ошибке.", exc_info=True)
        finally:
            self.user_tasks.pop(user_id, None)
