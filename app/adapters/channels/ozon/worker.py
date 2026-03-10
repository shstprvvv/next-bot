import asyncio
import logging
from typing import Optional
from datetime import datetime
from dateutil import parser
from app.adapters.channels.ozon.client import OzonClient
from app.core.use_cases.answer_question import AnswerQuestionUseCase
from app.adapters.db.database_adapter import DatabaseAdapter
from app.core.domain.models.marketplace_message import MarketplaceMessage

logger = logging.getLogger(__name__)

class OzonQuestionsWorker:
    def __init__(self, ozon_client: OzonClient, use_case: AnswerQuestionUseCase, db_adapter: DatabaseAdapter, check_interval: int = 300):
        self.ozon_client = ozon_client
        self.use_case = use_case
        self.db_adapter = db_adapter
        self.check_interval = check_interval
        self.is_running = False
        
        # Фильтр по дате: обрабатываем вопросы только с 1 марта 2026 года
        self.min_date = datetime(2026, 3, 1)

    async def start(self):
        self.is_running = True
        logger.info(f"[OzonWorker-Questions] Запуск фоновой проверки вопросов Ozon (фильтр даты с {self.min_date.date()})...")
        
        while self.is_running:
            try:
                await self.process_new_questions()
            except Exception as e:
                logger.error(f"[OzonWorker-Questions] Глобальная ошибка в цикле: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)

    async def process_new_questions(self):
        logger.info("[OzonWorker-Questions] Отправляю запрос к API Ozon за новыми вопросами...")
        questions = await self.ozon_client.get_unanswered_questions()
        
        if not questions:
            logger.info("[OzonWorker-Questions] API Ozon вернул пустой список новых вопросов.")
            return
            
        processed_count = 0
        max_batch_size = 3 # Берем в работу не больше 3 вопросов за один цикл

        for q in questions:
            if processed_count >= max_batch_size:
                logger.info(f"[OzonWorker-Questions] Достигнут лимит обработки в {max_batch_size} вопроса за цикл. Остальные будут обработаны в следующем цикле.")
                break

            q_id = q.get("id") or q.get("question_id")
            q_text = q.get("text", "")
            sku = q.get("sku")
            product_name = q.get("product_name", sku if sku else "Неизвестный товар")
            created_at_str = q.get("created_at") or q.get("date") or q.get("published_at")
            
            if not q_id or not q_text:
                continue
                
            # Проверка даты создания вопроса
            if created_at_str:
                try:
                    created_dt = parser.parse(created_at_str).replace(tzinfo=None)
                    if created_dt < self.min_date:
                        logger.debug(f"[OzonWorker-Questions] Пропуск вопроса {q_id} (создан {created_dt.date()} < {self.min_date.date()})")
                        continue
                except Exception as e:
                    logger.warning(f"[OzonWorker-Questions] Ошибка парсинга даты '{created_at_str}' для вопроса {q_id}: {e}")
            else:
                logger.warning(f"[OzonWorker-Questions] У вопроса {q_id} нет даты создания, пропускаем (чтобы не ответить на старые).")
                continue
                
            q_id = str(q_id)
            db_id = f"ozon_question_{q_id}"

            # Проверяем, обрабатывали ли мы уже этот вопрос
            existing_msg = self.db_adapter.get_message(db_id)
            if existing_msg and existing_msg.status in ("processing", "answered"):
                continue
                
            answers_count = q.get("answers_count", 0)
            if answers_count > 0:
                logger.info(f"[OzonWorker-Questions] Пропуск вопроса {q_id} (Уже есть {answers_count} ответов).")
                if not existing_msg:
                    message_record = MarketplaceMessage(
                        id=db_id,
                        marketplace="ozon",
                        message_type="question",
                        item_id=q_id,
                        product_name=product_name,
                        text=q_text,
                        status="answered",
                        created_at=datetime.now()
                    )
                    self.db_adapter.save_message(message_record)
                continue
                
            processed_count += 1
                
            # Создаем или обновляем запись в БД
            message_record = MarketplaceMessage(
                id=db_id,
                marketplace="ozon",
                message_type="question",
                item_id=q_id,
                product_name=product_name,
                text=q_text,
                status="processing",
                created_at=datetime.now()
            )
            self.db_adapter.save_message(message_record)

            full_query = f"Вопрос по товару '{product_name}': {q_text}"
            logger.info(f"[OzonWorker-Questions] Обработка вопроса {q_id}: {full_query}")

            try:
                # 1. Получаем ответ от нейросети
                answer = await self.use_case.execute(
                    user_id=db_id, 
                    question=full_query, 
                    history=[], 
                    source="ozon_question"
                )

                # 2. Отправляем ответ в Ozon
                success = await self.ozon_client.answer_question(question_id=q_id, text=answer, sku=sku)
                
                if success:
                    logger.info(f"[OzonWorker-Questions] Ответ на вопрос {q_id} успешно опубликован.")
                    self.db_adapter.update_status(db_id, "answered", answer_text=answer)
                else:
                    logger.warning(f"[OzonWorker-Questions] Не удалось опубликовать ответ на вопрос {q_id}.")
                    self.db_adapter.update_status(db_id, "failed")
            except Exception as e:
                logger.error(f"[OzonWorker-Questions] Ошибка обработки вопроса {q_id}: {e}")
                self.db_adapter.update_status(db_id, "failed")
            
            await asyncio.sleep(2)

    def stop(self):
        self.is_running = False
        logger.info("[OzonWorker-Questions] Остановка...")
