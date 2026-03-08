import asyncio
import logging
from typing import Optional
from datetime import datetime
from dateutil import parser
from app.adapters.channels.ozon.client import OzonClient
from app.core.use_cases.reply_to_feedback import ReplyToFeedbackUseCase
from app.adapters.db.database_adapter import DatabaseAdapter
from app.core.domain.models.marketplace_message import MarketplaceMessage

logger = logging.getLogger(__name__)

class OzonReviewsWorker:
    def __init__(self, ozon_client: OzonClient, use_case: ReplyToFeedbackUseCase, db_adapter: DatabaseAdapter, check_interval: int = 300):
        self.ozon_client = ozon_client
        self.use_case = use_case
        self.db_adapter = db_adapter
        self.check_interval = check_interval
        self.is_running = False
        
        # Фильтр по дате: обрабатываем отзывы только с 1 марта 2026 года
        self.min_date = datetime(2026, 3, 1)

    async def start(self):
        self.is_running = True
        logger.info(f"[OzonWorker-Reviews] Запуск фоновой проверки отзывов Ozon (фильтр даты с {self.min_date.date()})...")
        
        while self.is_running:
            try:
                await self.process_new_reviews()
            except Exception as e:
                logger.error(f"[OzonWorker-Reviews] Глобальная ошибка в цикле: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)

    async def process_new_reviews(self):
        logger.info("[OzonWorker-Reviews] Отправляю запрос к API Ozon за новыми отзывами...")
        reviews = await self.ozon_client.get_unanswered_reviews()
        
        if not reviews:
            logger.info("[OzonWorker-Reviews] API Ozon вернул пустой список новых отзывов.")
            return
            
        processed_count = 0
        max_batch_size = 3 # Берем в работу не больше 3 отзывов за один цикл

        for r in reviews:
            if processed_count >= max_batch_size:
                logger.info(f"[OzonWorker-Reviews] Достигнут лимит обработки в {max_batch_size} отзыва за цикл. Остальные будут обработаны в следующем цикле.")
                break

            r_id = r.get("id") or r.get("uuid")
            r_text = r.get("text", "")
            r_rating = r.get("rating", 0)
            sku = r.get("sku")
            product_name = r.get("product_name", sku if sku else "Неизвестный товар")
            created_at_str = r.get("published_at") or r.get("created_at") or r.get("date")
            
            if not r_id:
                continue
                
            # Проверка даты создания отзыва
            if created_at_str:
                try:
                    created_dt = parser.parse(created_at_str).replace(tzinfo=None)
                    if created_dt < self.min_date:
                        logger.debug(f"[OzonWorker-Reviews] Пропуск отзыва {r_id} (создан {created_dt.date()} < {self.min_date.date()})")
                        continue
                except Exception as e:
                    logger.warning(f"[OzonWorker-Reviews] Ошибка парсинга даты '{created_at_str}' для отзыва {r_id}: {e}")
            else:
                logger.warning(f"[OzonWorker-Reviews] У отзыва {r_id} нет даты публикации, пропускаем (чтобы не ответить на старые).")
                continue
                
            r_id = str(r_id)
            db_id = f"ozon_review_{r_id}"

            # Проверяем, обрабатывали ли мы уже этот отзыв
            existing_msg = self.db_adapter.get_message(db_id)
            if existing_msg and existing_msg.status in ("processing", "answered"):
                continue

            # Фильтрация отзывов: пропускаем 5 звезд или пустые отзывы
            if r_rating == 5:
                logger.info(f"[OzonWorker-Reviews] Пропуск отзыва {r_id} (Оценка: 5 звезд).")
                continue
                
            if not r_text.strip():
                logger.info(f"[OzonWorker-Reviews] Пропуск отзыва {r_id} (Оценка: {r_rating}, но нет текста).")
                continue
                
            processed_count += 1
                
            # Создаем или обновляем запись в БД
            message_record = MarketplaceMessage(
                id=db_id,
                marketplace="ozon",
                message_type="review",
                item_id=r_id,
                product_name=str(product_name),
                text=r_text,
                status="processing",
                created_at=datetime.now()
            )
            self.db_adapter.save_message(message_record)

            logger.info(f"[OzonWorker-Reviews] Обработка отзыва {r_id} (Оценка: {r_rating}): {r_text}")

            try:
                # 1. Получаем ответ от нейросети, используя специализированный юзкейс для отзывов
                answer = await self.use_case.execute(
                    review_text=r_text, 
                    valuation=r_rating, 
                    product_name=product_name
                )

                # 2. Отправляем ответ в Ozon
                success = await self.ozon_client.answer_review(review_id=r_id, text=answer)
                
                if success:
                    logger.info(f"[OzonWorker-Reviews] Ответ на отзыв {r_id} успешно опубликован.")
                    self.db_adapter.update_status(db_id, "answered", answer_text=answer)
                else:
                    logger.warning(f"[OzonWorker-Reviews] Не удалось опубликовать ответ на отзыв {r_id}.")
                    self.db_adapter.update_status(db_id, "failed")
            except Exception as e:
                logger.error(f"[OzonWorker-Reviews] Ошибка обработки отзыва {r_id}: {e}")
                self.db_adapter.update_status(db_id, "failed")
            
            await asyncio.sleep(2)

    def stop(self):
        self.is_running = False
        logger.info("[OzonWorker-Reviews] Остановка...")
