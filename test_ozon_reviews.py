import asyncio
import logging
from dotenv import load_dotenv

from app.config import load_config
from app.logging_config import setup_logging
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.faiss_adapter import FAISSRetrieverAdapter
from app.core.use_cases.reply_to_feedback import ReplyToFeedbackUseCase
from app.adapters.db.database_adapter import DatabaseAdapter
from app.adapters.channels.ozon.reviews_worker import OzonReviewsWorker

# Настраиваем логирование
setup_logging()
logger = logging.getLogger(__name__)

class MockOzonReviewsClient:
    def __init__(self):
        self.reviews_returned = False

    async def get_unanswered_reviews(self):
        if not self.reviews_returned:
            self.reviews_returned = True
            logger.info("[MockOzonReviewsClient] Отдаю тестовые отзывы...")
            return [
                {
                    "uuid": "test_r_1",
                    "text": "Отличная приставка, все летает!",
                    "rating": 5,
                    "product_name": "Смарт ТВ приставка NEXT",
                    "sku": "NEXT-BOX-1",
                    "published_at": "2026-03-08T10:00:00Z"
                },
                {
                    "uuid": "test_r_2",
                    "text": "",
                    "rating": 4,
                    "product_name": "Смарт ТВ приставка NEXT",
                    "sku": "NEXT-BOX-1",
                    "published_at": "2026-03-08T11:00:00Z"
                },
                {
                    "uuid": "test_r_3",
                    "text": "Ужас, тормозит видео на ютубе и пульт плохо реагирует.",
                    "rating": 2,
                    "product_name": "Смарт ТВ приставка NEXT",
                    "sku": "NEXT-BOX-1",
                    "published_at": "2026-03-08T12:00:00Z"
                }
            ]
        logger.info("[MockOzonReviewsClient] Отзывов больше нет.")
        return []

    async def answer_review(self, review_id: str, text: str):
        logger.info(f"[MockOzonReviewsClient] 🚀 Отправлен ответ на Ozon (ID: {review_id}):\n{text}\n")
        return True

async def main():
    load_dotenv()
    cfg = load_config()

    logger.info("=== Инициализация компонентов для теста Ozon Reviews ===")
    
    # 1. Настоящие LLM и Retriever для генерации реального ответа
    llm_adapter = LangChainLLMAdapter(
        api_key=cfg.get("OPENAI_API_KEY"),
        base_url=cfg.get("OPENAI_API_BASE"),
        model_name=cfg.get("OPENAI_MODEL_NAME"),
        temperature=0.0
    )
    
    retriever_adapter = FAISSRetrieverAdapter(
        index_path="faiss_index",
        knowledge_base_path="knowledge_base.md",
        openai_api_key=cfg.get("OPENAI_API_KEY"),
        openai_api_base=cfg.get("OPENAI_API_BASE")
    )
    
    # Используем UseCase для отзывов
    use_case = ReplyToFeedbackUseCase(llm=llm_adapter, retriever=retriever_adapter)
    
    # 2. Изолированная тестовая БД
    db_adapter = DatabaseAdapter(db_path="test_smart_bot.db")
    
    # Очищаем старые записи для чистоты эксперимента
    try:
        with db_adapter._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM marketplace_messages WHERE id LIKE 'ozon_review_test_r_%'")
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка очистки БД: {e}")
    
    # 3. Мок-клиент Ozon
    mock_client = MockOzonReviewsClient()
    
    # 4. Воркер отзывов
    worker = OzonReviewsWorker(
        ozon_client=mock_client,
        use_case=use_case,
        db_adapter=db_adapter,
        check_interval=2
    )

    logger.info("=== Запуск воркера отзывов Ozon ===")
    
    # Запускаем воркер в фоне
    worker_task = asyncio.create_task(worker.start())
    
    # Ждем 10 секунд, чтобы воркер успел обработать отзывы
    await asyncio.sleep(10)
    
    worker.stop()
    await worker_task
    
    logger.info("=== Проверка записей в Базе Данных ===")
    # Проверяем, что тест_r_3 обработан
    msg3 = db_adapter.get_message("ozon_review_test_r_3")
    if msg3:
        logger.info(f"Найдено сообщение в БД для test_r_3: Статус={msg3.status}")
        logger.info(f"Текст сохраненного ответа:\n{msg3.answer_text}")
    else:
        logger.error("Сообщение test_r_3 не найдено в БД! (Хотя должно было быть обработано)")

    # Убеждаемся, что test_r_1 и test_r_2 НЕ были сохранены/обработаны
    msg1 = db_adapter.get_message("ozon_review_test_r_1")
    if msg1:
        logger.error("Сообщение test_r_1 найдено в БД! А ДОЛЖНО БЫЛО БЫТЬ ПРОПУЩЕНО (5 звезд).")
    else:
        logger.info("Отлично, test_r_1 (5 звезд) успешно пропущен.")
        
    msg2 = db_adapter.get_message("ozon_review_test_r_2")
    if msg2:
        logger.error("Сообщение test_r_2 найдено в БД! А ДОЛЖНО БЫЛО БЫТЬ ПРОПУЩЕНО (без текста).")
    else:
        logger.info("Отлично, test_r_2 (без текста) успешно пропущен.")

if __name__ == "__main__":
    asyncio.run(main())
