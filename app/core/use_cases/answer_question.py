from dataclasses import dataclass
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever
from app.prompts.qa_prompt import build_qa_prompt
import logging

@dataclass
class AnswerQuestionUseCase:
    llm: LLMClient
    retriever: KnowledgeRetriever
    
    async def execute(self, user_id: int | str, question: str, history: list[str] = None, source: str = "telegram") -> str:
        """
        Главный сценарий:
        1. Переписать запрос с учетом контекста (ТВ приставки / приложение).
        2. Найти информацию в базе по переписанному запросу.
        3. Собрать промпт.
        4. Получить ответ от LLM.
        """
        if history is None:
            history = []

        # Передаем в контекст последние 10 сообщений диалога
        history_text = "\n".join(history[-10:]) if history else "Нет истории"

        # 1. Переписываем запрос (Context Enrichment)
        if source == "wb":
            reformulate_prompt = f"""Ты — умный маршрутизатор запросов в техподдержке. 
Мы продаем Смарт ТВ приставки на Wildberries. ВАЖНО: Мы здесь НЕ обслуживаем приложение с ТВ-каналами. Все вопросы касаются только настройки, подключения и работы ТВ-приставки.

Учитывая историю диалога и новый вопрос, перепиши вопрос клиента в идеальный поисковый запрос для базы знаний.
- Раскрой все местоимения (он, она, это), опираясь на историю.
- Если клиент не уточнил, добавь контекст, что речь скорее всего про Смарт ТВ приставку.
- Не отвечай на вопрос! Просто напиши ОДНУ фразу — поисковый запрос.

История диалога:
{history_text}

Новый вопрос клиента: {question}

Поисковый запрос:"""
        else:
            reformulate_prompt = f"""Ты — умный маршрутизатор запросов в техподдержке (Telegram). 
Мы полностью поддерживаем Смарт ТВ приставки NEXT и приложение с ТВ-каналами NEXT TV.

Учитывая историю диалога и новый вопрос, перепиши вопрос клиента в идеальный поисковый запрос для базы знаний.
- Раскрой все местоимения (он, она, это), опираясь на историю.
- Если клиент не уточнил, добавь контекст, что речь скорее всего про Смарт ТВ приставку или ТВ-приложение.
- Не отвечай на вопрос! Просто напиши ОДНУ фразу — поисковый запрос.

История диалога:
{history_text}

Новый вопрос клиента: {question}

Поисковый запрос:"""

        logging.info(f"[UseCase] Исходный вопрос: {question}")
        try:
            # Делаем быстрый запрос к LLM для получения идеальной поисковой фразы
            search_query = await self.llm.generate(reformulate_prompt)
            search_query = search_query.strip(' \n"')
            logging.info(f"[UseCase] Переписанный запрос для FAISS: {search_query}")
        except Exception as e:
            logging.error(f"[UseCase] Ошибка переписывания запроса, использую оригинал. Ошибка: {e}")
            search_query = question # Fallback, если что-то пошло не так

        # 2. Поиск в базе знаний
        chunks = self.retriever.retrieve(query=search_query)
        
        if not chunks:
            logging.warning("[UseCase] Ничего не найдено в базе знаний.")
            context = "Нет доступной информации в базе знаний."
        else:
            context = "\n\n".join([c.content for c in chunks])
            logging.info(f"[UseCase] Найдено {len(chunks)} фрагментов.")

        # 3. Сборка промпта
        prompt = build_qa_prompt(question, context, history_text, source=source)

        # 4. Генерация ответа
        logging.info("[UseCase] Генерирую ответ через LLM...")
        try:
            answer = await self.llm.generate(prompt)
            return answer.strip()
        except Exception as e:
            logging.error(f"[UseCase] Ошибка LLM: {e}", exc_info=True)
            return "К сожалению, произошла техническая ошибка при генерации ответа."
