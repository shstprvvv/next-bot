import asyncio
import logging
from datetime import datetime, timedelta
from app.adapters.channels.wildberries.client import WBClient
from app.core.use_cases.answer_question import AnswerQuestionUseCase

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
            
        logger.info(f"[WBWorker] Будут обрабатываться вопросы, созданные после: {self.start_date}")

    async def start(self):
        self.is_running = True
        logger.info("[WBWorker] Запуск фоновой проверки вопросов Wildberries...")
        
        while self.is_running:
            try:
                await self.process_new_questions()
            except Exception as e:
                logger.error(f"[WBWorker] Глобальная ошибка в цикле: {e}", exc_info=True)
            
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
            logger.info(f"[WBWorker] Обработка вопроса {q_id}: {full_query}")

            # 1. Получаем ответ от нейросети
            # Передаем user_id=0 или специальный ID для WB, чтобы не смешивать с историей Telegram
            answer = await self.use_case.execute(user_id=f"wb_question_{q_id}", question=full_query, history=[])

            # 2. Отправляем ответ в WB
            success = await self.wb_client.send_answer(id=q_id, text=answer)
            
            if success:
                logger.info(f"[WBWorker] Ответ на {q_id} успешно опубликован.")
            else:
                logger.warning(f"[WBWorker] Не удалось опубликовать ответ на {q_id}.")
            
            # Небольшая пауза между ответами, чтобы не спамить
            await asyncio.sleep(2)

    def stop(self):
        self.is_running = False
        logger.info("[WBWorker] Остановка...")
