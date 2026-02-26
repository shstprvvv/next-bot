import asyncio
import logging
import base64
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

        # 3. Обработка фото/видео и текста
        image_base64 = None
        has_media = bool(event.media) or bool(getattr(event.message, 'photo', None)) or bool(getattr(event.message, 'document', None))
        
        if has_media:
            logger.info(f"[Telegram] Получено медиа от {chat_id}, пытаюсь скачать...")
            try:
                # Скачиваем медиа в память
                media_bytes = await self.client.download_media(event.message, file=bytes)
                if media_bytes:
                    image_base64 = base64.b64encode(media_bytes).decode('utf-8')
                    logger.info(f"[Telegram] Медиа успешно скачано и сконвертировано в base64.")
            except Exception as e:
                logger.error(f"[Telegram] Ошибка при скачивании медиа: {e}")
                # Если не получилось скачать, просто извинимся как раньше
                await event.reply("Вижу ваш файл! 📷 К сожалению, я не смог его открыть. Опишите, пожалуйста, проблему словами — что именно вы видите на экране?")
                return

        # Если текста нет, а картинка есть, ставим заглушку для логики
        if not text and image_base64:
            text = "[Пользователь прислал только фото без текста]"

        logger.info(f"[Telegram] Сообщение от {chat_id}: '{text}'")

        # Сохраняем сообщение и картинку (берем последнюю присланную)
        self.user_messages[chat_id].append({"text": text, "image": image_base64})
        
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
            
        messages_data = self.user_messages.pop(user_id)
        # Склеиваем весь текст
        full_message = " ".join([m["text"] for m in messages_data if m["text"]])
        # Берем последнюю картинку из серии (если их было несколько)
        image_base64 = next((m["image"] for m in reversed(messages_data) if m["image"]), None)

        logger.info(f"[Telegram] Обработка для {user_id}: '{full_message}' (с картинкой: {bool(image_base64)})")
        
        # Здесь мы достаем историю диалога из памяти (пока в ОЗУ)
        history = self.chat_history[user_id].copy()
        
        # Увеличиваем счетчик сообщений для отслеживания "тупняков"
        self.user_attempts[user_id] += 1
        
        # Вызов Use Case
        try:
            # Уведомляем Telegram, что "печатаем" (опционально)
            try:
                input_chat = await event.get_input_chat()
                async with self.client.action(input_chat, 'typing'):
                    answer = await self.use_case.execute(user_id, full_message, history, source="telegram", image_base64=image_base64)
            except ValueError as e:
                logger.warning(f"[Telegram] Ошибка при отправке typing action: {e}. Выполняем без него.")
                answer = await self.use_case.execute(user_id, full_message, history, source="telegram", image_base64=image_base64)
            
            # ЗАГЛУШКА НА ГЛУПЫЕ ОТВЕТЫ
            stop_phrases = [
                "нет готового решения", 
                "к сожалению, у меня нет",
                "изучим проблему более детально",
                "я всего лишь",
                "я искусственный интеллект",
                "я языковая модель"
            ]
            
            if any(phrase in answer.lower() for phrase in stop_phrases):
                logger.warning(f"[Telegram] Сработала заглушка стоп-слов! Исходный ответ бота: {answer}")
                answer = "Уточните, пожалуйста, на каком этапе возникает проблема? Какие индикаторы горят на самой приставке? Что именно пишет на экране телевизора?"

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
            # Убрали отправку сообщения об ошибке "Произошла ошибка при обработке вашего запроса."
        finally:
            self.user_tasks.pop(user_id, None)
