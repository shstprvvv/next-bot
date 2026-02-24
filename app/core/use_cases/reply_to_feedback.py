from dataclasses import dataclass
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever
from app.prompts.feedback_prompt import build_feedback_prompt
import logging

@dataclass
class ReplyToFeedbackUseCase:
    llm: LLMClient
    retriever: KnowledgeRetriever
    
    async def execute(self, review_text: str, valuation: int, product_name: str) -> str:
        """
        Сценарий ответа на отзыв:
        1. Если оценка низкая или есть текст, ищем контекст в базе.
        2. Формируем промпт.
        3. Генерируем ответ.
        """
        
        # 1. Поиск в базе знаний (только если есть текст отзыва)
        context = ""
        if review_text and len(review_text) > 3:
            logging.info(f"[FeedbackUseCase] Ищу в базе по отзыву: {review_text[:50]}...")
            chunks = self.retriever.retrieve(query=review_text)
            
            if chunks:
                context = "\n\n".join([c.content for c in chunks])
                logging.info(f"[FeedbackUseCase] Найдено {len(chunks)} фрагментов.")
        
        # 2. Сборка промпта
        prompt = build_feedback_prompt(
            text=review_text, 
            valuation=valuation, 
            product_name=product_name, 
            context=context
        )

        # 3. Генерация ответа
        logging.info(f"[FeedbackUseCase] Генерирую ответ для оценки {valuation}...")
        try:
            answer = await self.llm.generate(prompt)
            return answer.strip()
        except Exception as e:
            logging.error(f"[FeedbackUseCase] Ошибка LLM: {e}", exc_info=True)
            return "Спасибо за ваш отзыв! Мы примем его во внимание." # Fallback
