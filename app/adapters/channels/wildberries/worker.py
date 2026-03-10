import asyncio
import logging
import base64
from typing import Optional
from datetime import datetime, timedelta
from app.adapters.channels.wildberries.client import WBClient
from app.core.use_cases.answer_question import AnswerQuestionUseCase
from app.core.use_cases.reply_to_feedback import ReplyToFeedbackUseCase

logger = logging.getLogger(__name__)

class WBQuestionsWorker:
    def __init__(self, wb_client: WBClient, use_case: AnswerQuestionUseCase, check_interval: int = 300, ignore_older_than_days: int = 0):
        self.wb_client = wb_client
        self.use_case = use_case
        self.check_interval = check_interval
        self.is_running = False
        
        # Дата, начиная с которой мы смотрим вопросы.
        # Если 0 - берем текущее время запуска (только новые).
        # Если > 0 - берем вопросы за последние N дней.
        if ignore_older_than_days > 0:
            self.start_date = datetime.now() - timedelta(days=ignore_older_than_days)
        else:
            self.start_date = datetime.now()
            
        logger.info(f"[WBWorker-Questions] Будут обрабатываться вопросы, созданные после: {self.start_date}")

    async def start(self):
        self.is_running = True
        logger.info("[WBWorker-Questions] Запуск фоновой проверки вопросов Wildberries...")
        
        while self.is_running:
            try:
                await self.process_new_questions()
            except Exception as e:
                logger.error(f"[WBWorker-Questions] Глобальная ошибка в цикле: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)

    async def process_new_questions(self):
        # Запрашиваем только вопросы, пришедшие после даты старта бота
        questions = await self.wb_client.get_unanswered_questions(date_from=self.start_date)
        
        if not questions:
            return

        for q in questions:
            q_id = q.get("id")
            q_text = q.get("text", "")
            product_name = q.get("productDetails", {}).get("productName", "")
            
            if not q_id or not q_text:
                continue

            # Формируем контекст для LLM
            full_query = f"Вопрос по товару '{product_name}': {q_text}"
            logger.info(f"[WBWorker-Questions] Обработка вопроса {q_id}: {full_query}")

            # 1. Получаем ответ от нейросети
            answer = await self.use_case.execute(user_id=f"wb_question_{q_id}", question=full_query, history=[], source="wb")

            # 2. Отправляем ответ в WB
            success = await self.wb_client.answer_question(id=q_id, text=answer)
            
            if success:
                logger.info(f"[WBWorker-Questions] Ответ на вопрос {q_id} успешно опубликован.")
            else:
                logger.warning(f"[WBWorker-Questions] Не удалось опубликовать ответ на вопрос {q_id}.")
            
            # Небольшая пауза между ответами
            await asyncio.sleep(2)

    def stop(self):
        self.is_running = False
        logger.info("[WBWorker-Questions] Остановка...")

class WBChatWorker:
    def __init__(self, wb_client: WBClient, use_case: AnswerQuestionUseCase, check_interval: int = 300):
        self.wb_client = wb_client
        self.use_case = use_case
        self.check_interval = check_interval
        self.is_running = False
        # Для инкрементального получения событий (сохраняем в файл, чтобы не терять при перезапуске)
        self.token_file = "sessions/wb_chat_next_token.txt"
        self.next_token: Optional[int] = self._load_token()
        self.chat_history = {} # История диалогов в памяти

    def _load_token(self) -> Optional[int]:
        try:
            import os
            if os.path.exists(self.token_file):
                with open(self.token_file, "r") as f:
                    val = f.read().strip()
                    if val:
                        return int(val)
        except Exception as e:
            logger.error(f"[WBWorker-Chat] Ошибка загрузки токена: {e}")
        return None

    def _save_token(self, token: int):
        try:
            with open(self.token_file, "w") as f:
                f.write(str(token))
        except Exception as e:
            logger.error(f"[WBWorker-Chat] Ошибка сохранения токена: {e}")

    async def _fast_forward(self):
        logger.info("[WBWorker-Chat] Инициализация: перемотка старых событий (это может занять несколько секунд)...")
        while True:
            try:
                data = await self.wb_client.get_chat_events(next_token=self.next_token)
                if not data or "result" not in data:
                    break
                    
                result = data["result"]
                events = result.get("events", [])
                
                if "next" in result and result["next"] != self.next_token:
                    self.next_token = result["next"]
                    self._save_token(self.next_token)
                    if events:
                        logger.info(f"[WBWorker-Chat] Перемотка: пропущено {len(events)} событий. Токен: {self.next_token}")
                else:
                    break
                    
                if not events:
                    break
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"[WBWorker-Chat] Ошибка при перемотке: {e}")
                break
        logger.info(f"[WBWorker-Chat] Перемотка завершена. Актуальный токен: {self.next_token}")

    async def start(self):
        self.is_running = True
        logger.info("[WBWorker-Chat] Запуск фоновой проверки чатов Wildberries...")
        
        if self.next_token is None:
            await self._fast_forward()
        
        while self.is_running:
            try:
                await self.process_new_messages()
            except Exception as e:
                logger.error(f"[WBWorker-Chat] Глобальная ошибка в цикле: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)

    async def process_new_messages(self):
        # Получаем события чатов
        data = await self.wb_client.get_chat_events(next_token=self.next_token)
        
        if not data or "result" not in data:
            return

        result = data["result"]
        events = result.get("events", [])
        
        # Обновляем next_token для следующего запроса
        if "next" in result:
            new_token = result["next"]
            self.next_token = new_token
            self._save_token(new_token)

        for event in events:
            try:
                # Нас интересуют только входящие сообщения от клиентов
                event_type = str(event.get("eventType", "")).lower()
                sender = str(event.get("sender", "")).lower()
                
                if event_type != "message":
                    continue
                    
                # Разрешаем "client", "buyer", "customer" на случай изменений в API
                if sender not in ["client", "buyer", "customer"]:
                    continue

                chat_id = event.get("chatID") or event.get("chatId")
                reply_sign = event.get("replySign")
                message_data = event.get("message", {})
                text = message_data.get("text", "")
                
                # Извлекаем картинки, если есть
                images = message_data.get("attachments", {}).get("images", [])
                image_base64 = None
                
                if not chat_id:
                    logger.warning(f"[WBWorker-Chat] Пропуск: нет chat_id в событии: {event}")
                    continue
                    
                if not reply_sign:
                    logger.warning(f"[WBWorker-Chat] Пропуск: нет reply_sign для чата {chat_id}. Это может быть системное сообщение или ошибка WB API.")
                    continue
                    
                if not text and not images:
                    # Ни текста, ни картинок
                    continue

                logger.info(f"[WBWorker-Chat] Новое сообщение в чате {chat_id}: текст='{text}', картинок={len(images)}")
                
                if images:
                    # Берем первую картинку для распознавания
                    img_info = images[0]
                    download_id = img_info.get("downloadID")
                    if download_id:
                        logger.info(f"[WBWorker-Chat] Скачиваю картинку {download_id}...")
                        img_bytes = await self.wb_client.download_chat_file(download_id)
                        if img_bytes:
                            image_base64 = base64.b64encode(img_bytes).decode('utf-8')
                            logger.info(f"[WBWorker-Chat] Картинка успешно скачана и переведена в base64.")

                # Если пришла только картинка без текста, и мы не смогли её скачать
                if not text and not image_base64:
                    logger.warning(f"[WBWorker-Chat] Итоговое сообщение от {chat_id} оказалось пустым (не удалось скачать медиа).")
                    await self.wb_client.send_chat_message(
                        chat_id=chat_id, 
                        text="Вижу ваш файл! К сожалению, я пока могу отвечать только на текст. Опишите, пожалуйста, проблему словами.", 
                        reply_sign=reply_sign
                    )
                    continue

                # Инициализируем историю для чата, если её нет
                if chat_id not in self.chat_history:
                    self.chat_history[chat_id] = []

                # 1. Получаем ответ от нейросети
                answer = await self.use_case.execute(
                    user_id=f"wb_chat_{chat_id}", 
                    question=text, 
                    history=self.chat_history[chat_id], 
                    source="wb_chat",
                    image_base64=image_base64
                )

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
                    logger.warning(f"[WBWorker-Chat] Сработала заглушка стоп-слов! Исходный ответ: {answer}")
                    answer = "Уточните, пожалуйста, на каком этапе возникает проблема? Какие индикаторы горят на самой приставке? Что именно пишет на экране телевизора?"

                # 2. Отправляем ответ в WB
                success = await self.wb_client.send_chat_message(chat_id=chat_id, text=answer, reply_sign=reply_sign)
                
                if success:
                    logger.info(f"[WBWorker-Chat] Ответ в чат {chat_id} успешно отправлен.")
                    self.chat_history[chat_id].append(f"Клиент: {text}")
                    self.chat_history[chat_id].append(f"Бот: {answer}")
                    
                    if len(self.chat_history[chat_id]) > 20:
                        self.chat_history[chat_id] = self.chat_history[chat_id][-20:]
                else:
                    logger.warning(f"[WBWorker-Chat] Не удалось отправить ответ в чат {chat_id}.")
                
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"[WBWorker-Chat] Ошибка при обработке события чата: {e}", exc_info=True)

    def stop(self):
        self.is_running = False
        logger.info("[WBWorker-Chat] Остановка...")

class WBFeedbacksWorker:
    def __init__(self, wb_client: WBClient, use_case: ReplyToFeedbackUseCase, check_interval: int = 300, ignore_older_than_days: int = 0):
        self.wb_client = wb_client
        self.use_case = use_case
        self.check_interval = check_interval
        self.is_running = False
        
        if ignore_older_than_days > 0:
            self.start_date = datetime.now() - timedelta(days=ignore_older_than_days)
        else:
            self.start_date = datetime.now()
            
        logger.info(f"[WBWorker-Feedbacks] Будут обрабатываться отзывы, созданные после: {self.start_date}")

    async def start(self):
        self.is_running = True
        logger.info("[WBWorker-Feedbacks] Запуск фоновой проверки отзывов Wildberries...")
        
        while self.is_running:
            try:
                await self.process_new_feedbacks()
            except Exception as e:
                logger.error(f"[WBWorker-Feedbacks] Глобальная ошибка в цикле: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)

    async def process_new_feedbacks(self):
        feedbacks = await self.wb_client.get_unanswered_feedbacks(date_from=self.start_date)
        
        if not feedbacks:
            return

        for fb in feedbacks:
            fb_id = fb.get("id")
            
            # В Wildberries текст отзыва может быть разбит на 3 поля: text (комментарий), pros (плюсы), cons (минусы)
            text_parts = []
            if fb.get("text"):
                text_parts.append(f"Комментарий: {fb.get('text')}")
            if fb.get("pros"):
                text_parts.append(f"Плюсы: {fb.get('pros')}")
            if fb.get("cons"):
                text_parts.append(f"Минусы: {fb.get('cons')}")
                
            fb_text = "\n".join(text_parts).strip()
            
            valuation = fb.get("productValuation", 5) # По умолчанию 5, если не указано
            product_name = fb.get("productDetails", {}).get("productName", "")
            
            if not fb_id:
                continue
            
            # НОВАЯ ЛОГИКА: Пропускаем отзывы с оценкой 5 звезд или отзывы без текста
            if valuation == 5:
                logger.info(f"[WBWorker-Feedbacks] Пропуск отзыва {fb_id} (Оценка: 5 звезд).")
                continue
                
            if not fb_text:
                logger.info(f"[WBWorker-Feedbacks] Пропуск отзыва {fb_id} (Оценка: {valuation}, но нет текста).")
                continue
            
            logger.info(f"[WBWorker-Feedbacks] Обработка отзыва {fb_id} (Оценка: {valuation}): {fb_text}")

            # 1. Генерируем ответ
            answer = await self.use_case.execute(
                review_text=fb_text, 
                valuation=valuation, 
                product_name=product_name
            )

            # 2. Отправляем ответ
            logger.info(f"[WBWorker-Feedbacks] Пытаюсь отправить ответ на отзыв {fb_id} в WB API...")
            success = await self.wb_client.answer_feedback(id=fb_id, text=answer)
            
            if success:
                logger.info(f"[WBWorker-Feedbacks] ✅ УСПЕШНО! Ответ на отзыв {fb_id} опубликован в WB. Текст ответа: '{answer[:100]}...'")
            else:
                logger.error(f"[WBWorker-Feedbacks] ❌ ОШИБКА! WB API вернул False. Не удалось опубликовать ответ на отзыв {fb_id}.")
            
            await asyncio.sleep(2)

    def stop(self):
        self.is_running = False
        logger.info("[WBWorker-Feedbacks] Остановка...")
