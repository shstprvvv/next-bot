import asyncio
import logging
from dotenv import load_dotenv

from app.config import load_config
from app.logging_config import setup_logging
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.faiss_adapter import FAISSRetrieverAdapter
from app.core.use_cases.answer_question import AnswerQuestionUseCase
from app.adapters.db.database_adapter import DatabaseAdapter
from app.adapters.channels.ozon.worker import OzonQuestionsWorker

# Настраиваем логирование
setup_logging()
logger = logging.getLogger(__name__)

class MockOzonClient:
    def __init__(self):
        self.questions_returned = False

    async def get_unanswered_questions(self):
        if not self.questions_returned:
            self.questions_returned = True
            logger.info("[MockOzonClient] Отдаю тестовый вопрос...")
            return [
                {
                    "question_id": "test_q_12345",
                    "text": "Здравствуйте! Подскажите, работает ли YouTube на этой приставке?",
                    "product_name": "Смарт ТВ приставка NEXT",
                    "sku": "NEXT-BOX-1"
                }
            ]
        logger.info("[MockOzonClient] Вопросов больше нет.")
        return []

    async def answer_question(self, question_id: str, text: str):
        logger.info(f"[MockOzonClient] 🚀 Отправлен ответ на Ozon (ID: {question_id}):\n{text}\n")
        return True

async def main():
    load_dotenv()
    cfg = load_config()

    logger.info("=== Инициализация компонентов для теста ===")
    
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
    
    use_case = AnswerQuestionUseCase(llm=llm_adapter, retriever=retriever_adapter)
    
    # 2. Изолированная тестовая БД
    db_adapter = DatabaseAdapter(db_path="test_smart_bot.db")
    
    # 3. Мок-клиент Ozon
    mock_client = MockOzonClient()
    
    # 4. Воркер
    worker = OzonQuestionsWorker(
        ozon_client=mock_client,
        use_case=use_case,
        db_adapter=db_adapter,
        check_interval=2
    )

    logger.info("=== Запуск воркера Ozon ===")
    
    # Запускаем воркер в фоне
    worker_task = asyncio.create_task(worker.start())
    
    # Ждем 10 секунд, чтобы воркер успел обработать вопрос
    await asyncio.sleep(10)
    
    worker.stop()
    await worker_task
    
    logger.info("=== Проверка записи в Базе Данных ===")
    msg = db_adapter.get_message("ozon_question_test_q_12345")
    if msg:
        logger.info(f"Найдено сообщение в БД: ID={msg.id}, Статус={msg.status}")
        logger.info(f"Текст вопроса: {msg.text}")
        logger.info(f"Текст сохраненного ответа: {msg.answer_text}")
    else:
        logger.error("Сообщение не найдено в БД!")

if __name__ == "__main__":
    asyncio.run(main())
