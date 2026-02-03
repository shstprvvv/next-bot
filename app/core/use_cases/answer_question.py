from dataclasses import dataclass
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever
from app.prompts.qa_prompt import build_qa_prompt
import logging

@dataclass
class AnswerQuestionUseCase:
    llm: LLMClient
    retriever: KnowledgeRetriever
    
    async def execute(self, user_id: int, question: str, history: list[str] = None) -> str:
        """
        Главный сценарий:
        1. Найти информацию в базе.
        2. Собрать промпт.
        3. Получить ответ от LLM.
        """
        if history is None:
            history = []

        # 1. Поиск в базе знаний
        logging.info(f"[UseCase] Ищу в базе: {question}")
        chunks = self.retriever.retrieve(query=question)
        
        if not chunks:
            logging.warning("[UseCase] Ничего не найдено в базе знаний.")
            context = "Нет доступной информации в базе знаний."
        else:
            context = "\n\n".join([c.content for c in chunks])
            logging.info(f"[UseCase] Найдено {len(chunks)} фрагментов.")

        # 2. Подготовка истории (берем последние 3 сообщения для контекста)
        # В будущем здесь может быть логика суммаризации
        history_text = "\n".join(history[-3:]) if history else "Нет истории"

        # 3. Сборка промпта
        prompt = build_qa_prompt(question, context, history_text)

        # 4. Генерация ответа
        logging.info("[UseCase] Генерирую ответ через LLM...")
        try:
            answer = await self.llm.generate(prompt)
            return answer.strip()
        except Exception as e:
            logging.error(f"[UseCase] Ошибка LLM: {e}", exc_info=True)
            return "К сожалению, произошла техническая ошибка при генерации ответа."
