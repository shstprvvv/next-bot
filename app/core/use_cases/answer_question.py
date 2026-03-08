from dataclasses import dataclass
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever
from app.prompts.qa_prompt import build_qa_prompt
import logging

@dataclass
class AnswerQuestionUseCase:
    llm: LLMClient
    retriever: KnowledgeRetriever
    
    async def execute(self, user_id: int | str, question: str, history: list[str] = None, source: str = "telegram", image_base64: str = None) -> str:
        """
        Главный сценарий:
        1. Распознавание картинки и переписывание запроса в поисковый (схлопнуто в 1 запрос для скорости).
        2. Найти информацию в базе по переписанному запросу.
        3. Собрать промпт.
        4. Получить ответ от LLM.
        """
        if history is None:
            history = []

        # Передаем в контекст последние 10 сообщений диалога
        history_text = "\n".join(history[-10:]) if history else "Нет истории"

        # 1. Распознавание картинки и переписывание запроса (Context Enrichment)
        
        # Базовые инструкции для маршрутизатора в зависимости от источника
        if source.startswith("wb"):
            router_context = "Мы продаем Смарт ТВ приставки на Wildberries. ВАЖНО: Мы здесь НЕ обслуживаем приложение с ТВ-каналами. Все вопросы касаются только настройки, подключения и работы ТВ-приставки."
        elif source == "ozon_question":
            router_context = "Мы продаем Смарт ТВ приставки на Ozon. ВАЖНО: Мы здесь НЕ обслуживаем приложение с ТВ-каналами. Все вопросы касаются только настройки, подключения и работы ТВ-приставки."
        elif source == "ozon_review":
            router_context = "Мы продаем Смарт ТВ приставки на Ozon. Клиент оставил отзыв. ВАЖНО: Мы здесь НЕ обслуживаем приложение с ТВ-каналами. Если в отзыве есть вопрос или жалоба, они касаются только настройки, подключения и работы ТВ-приставки."
        else:
            router_context = "Мы полностью поддерживаем Смарт ТВ приставки NEXT и приложение с ТВ-каналами NEXT TV."

        logging.info(f"[UseCase] Исходный вопрос: {question}")

        if image_base64:
            logging.info(f"[UseCase] Получено изображение, отправляю на совместный анализ и маршрутизацию (ускоренный флоу)...")
            router_prompt_text = f"""Ты — умный маршрутизатор запросов в техподдержке.
{router_context}

Клиент прислал фото своей проблемы. Твоя задача — изучить фото, историю диалога и вопрос клиента, а затем выдать:
1. Краткое описание проблемы на фото (текст ошибок, интерфейс, индикаторы).
2. Идеальный поисковый запрос для базы знаний.

Правила для поискового запроса:
- Удали из вопроса эмоции, маты, угрозы возвратом и "воду". Оставь только техническую суть проблемы.
- Раскрой все местоимения (он, она, это), опираясь на историю.
- Если клиент просто поздоровался, прислал смайлик или в его сообщении нет технического вопроса, напиши строго фразу: 'нет конкретной проблемы'.
- Если клиент не уточнил, добавь контекст, что речь скорее всего про Смарт ТВ приставку.

Формат ответа СТРОГО такой (два поля):
ОПИСАНИЕ: <твое краткое описание фото>
ЗАПРОС: <твой поисковый запрос>

История диалога:
{history_text}

Новый вопрос клиента: {question}"""
            
            messages = [
                {"type": "text", "text": router_prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ]
            
            try:
                response_text = await self.llm.generate(messages)
                logging.info(f"[UseCase] Ответ Vision+Router: {response_text}")
                
                desc_part = ""
                query_part = question
                
                if "ЗАПРОС:" in response_text:
                    parts = response_text.split("ЗАПРОС:")
                    desc_part = parts[0].replace("ОПИСАНИЕ:", "").strip()
                    query_part = parts[1].strip()
                else:
                    # Если LLM не соблюдала формат, считаем все описанием
                    desc_part = response_text
                
                image_description = desc_part
                search_query = query_part.strip(' \n"\'').strip()
                logging.info(f"[UseCase] Переписанный запрос для FAISS: {search_query}")
                
                if not question or question.strip() == "":
                    question = f"[Пользователь прислал только фото. Описание фото: {image_description}]"
                else:
                    question = f"[Пользователь прислал фото. Описание фото: {image_description}]\nТекст пользователя: {question}"
                    
            except Exception as e:
                logging.error(f"[UseCase] Ошибка при распознавании картинки и маршрутизации: {e}")
                search_query = question
                if not question or question.strip() == "":
                    question = "[Пользователь прислал фото, но я не смог его распознать]"
                else:
                    question = f"[Пользователь прислал фото, но я не смог его распознать]\nТекст пользователя: {question}"

        else:
            reformulate_prompt = f"""Ты — умный маршрутизатор запросов в техподдержке. 
{router_context}

Учитывая историю диалога и новый вопрос, перепиши вопрос клиента в идеальный поисковый запрос для базы знаний.
- Удали из вопроса лишние эмоции, маты, угрозы возвратом и "воду". Оставь только техническую суть проблемы.
- Раскрой все местоимения (он, она, это), опираясь на историю.
- Если клиент просто поздоровался, прислал смайлик или в его сообщении нет технического вопроса, напиши строго фразу: 'нет конкретной проблемы'.
- Если клиент не уточнил, добавь контекст, что речь скорее всего про Смарт ТВ приставку.
- Не отвечай на вопрос! Просто напиши ОДНУ фразу — поисковый запрос.

История диалога:
{history_text}

Новый вопрос клиента: {question}

Поисковый запрос:"""

            try:
                # Делаем быстрый запрос к LLM для получения идеальной поисковой фразы
                search_query = await self.llm.generate(reformulate_prompt)
                search_query = search_query.strip(' \n"\'').strip()
                logging.info(f"[UseCase] Переписанный запрос для FAISS: {search_query}")
            except Exception as e:
                logging.error(f"[UseCase] Ошибка переписывания запроса, использую оригинал. Ошибка: {e}")
                search_query = question # Fallback, если что-то пошло не так

        # 2. Поиск в базе знаний
        if search_query.lower() == "нет конкретной проблемы":
            chunks = []
            logging.info("[UseCase] В запросе нет конкретной проблемы, поиск в базе знаний пропущен.")
        else:
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
            logging.info(f"[UseCase] Сгенерированный ответ: {answer.strip()}")
            return answer.strip()
        except Exception as e:
            logging.error(f"[UseCase] Ошибка LLM: {e}", exc_info=True)
            return "К сожалению, произошла техническая ошибка при генерации ответа."
