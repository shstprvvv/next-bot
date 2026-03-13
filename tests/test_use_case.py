import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.core.use_cases.answer_question import AnswerQuestionUseCase
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever

class TestAnswerQuestionUseCase(unittest.IsolatedAsyncioTestCase):
    
    async def test_brand_context_routing(self):
        # Настраиваем моки
        mock_llm = AsyncMock(spec=LLMClient)
        mock_llm.generate.return_value = "переписанный_запрос"
        
        mock_retriever = MagicMock(spec=KnowledgeRetriever)
        mock_retriever.retrieve.return_value = []
        
        use_case = AnswerQuestionUseCase(llm=mock_llm, retriever=mock_retriever)
        
        # Тестируем вызов с brand_context
        await use_case.execute(
            user_id="123",
            question="Как настроить пульт?",
            brand_context="Мы магазин GamerStore, продаем игровые аксессуары."
        )
        
        # Проверяем, что в промпт для переписывания запроса попал нужный контекст
        calls = mock_llm.generate.call_args_list
        # Первый вызов generate - это маршрутизатор/переписывание (если нет картинки)
        router_prompt = calls[0][0][0]
        
        self.assertIn("Мы магазин GamerStore, продаем игровые аксессуары.", router_prompt)

if __name__ == '__main__':
    unittest.main()
