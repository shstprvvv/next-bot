from dataclasses import dataclass
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever
from app.prompts.feedback_prompt import build_feedback_prompt
import logging

from typing import Optional

@dataclass
class ReplyToFeedbackUseCase:
    llm: LLMClient
    retriever: KnowledgeRetriever
    client_config: Optional[dict] = None
    
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
            if self.client_config and self.client_config.get("id") != "next":
                brand = self.client_config.get("brand_name", "нашей компании")
                category = self.client_config.get("product_category", "наших товаров")
                router_context = f"Мы продаем {category} под брендом {brand}."
            else:
                router_context = "Мы продаем Смарт ТВ приставки на Wildberries. ВАЖНО: Мы здесь НЕ обслуживаем приложение с ТВ-каналами."

            reformulate_prompt = f"""Ты — умный маршрутизатор отзывов покупателей.
{router_context}
Товар: {product_name}. Оценка: {valuation} звезд.
Покупатель написал отзыв: "{review_text}"

Перепиши суть жалобы или вопроса из отзыва в четкий поисковый запрос для базы знаний техподдержки.
- Если жалуются на конкретную проблему (например, "зависает", "греется", "не работает пульт"), сделай из этого поисковый запрос (например: "почему приставка зависает").
- Если в отзыве нет конкретной проблемы, а просто общие эмоции, напиши "нет конкретной проблемы".
- Не отвечай на отзыв! Просто напиши ОДНУ фразу — поисковый запрос.

Поисковый запрос:"""

            logging.info(f"[FeedbackUseCase] Исходный отзыв: {review_text[:50]}...")
            try:
                # Делаем быстрый запрос к LLM для получения идеальной поисковой фразы
                search_query = await self.llm.generate(reformulate_prompt)
                search_query = search_query.strip(' \n"')
                logging.info(f"[FeedbackUseCase] Переписанный запрос для FAISS: {search_query}")
            except Exception as e:
                logging.error(f"[FeedbackUseCase] Ошибка переписывания запроса, использую оригинал. Ошибка: {e}")
                search_query = review_text
                
            if search_query.lower() not in ["нет конкретной проблемы", "нет конкретной проблемы.", ""]:
                chunks = self.retriever.retrieve(query=search_query)
                
                if chunks:
                    context = "\n\n".join([c.content for c in chunks])
                    logging.info(f"[FeedbackUseCase] Найдено {len(chunks)} фрагментов.")
        
        # 2. Сборка промпта
        prompt = build_feedback_prompt(
            text=review_text, 
            valuation=valuation, 
            product_name=product_name, 
            context=context,
            client_config=self.client_config
        )

        # 3. Генерация ответа
        logging.info(f"[FeedbackUseCase] Генерирую ответ для оценки {valuation}...")
        try:
            answer = await self.llm.generate(prompt)
            return answer.strip()
        except Exception as e:
            logging.error(f"[FeedbackUseCase] Ошибка LLM: {e}", exc_info=True)
            return "Спасибо за ваш отзыв! Мы примем его во внимание." # Fallback
