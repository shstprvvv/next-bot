import logging
import json
import re
import ast
from langchain.tools import Tool
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings
from wildberries_api import get_unanswered_feedbacks, get_unanswered_questions, post_feedback_answer

def create_knowledge_base_tool(api_key: str, base_url: str = None):
    """Создает и возвращает RAG-инструмент."""
    logging.info("[KnowledgeBase] Инициализация RAG-системы...")
    
    try:
        logging.info("[KnowledgeBase] Шаг 1: Загрузка knowledge_base.txt...")
        loader = TextLoader('knowledge_base.txt', encoding='utf-8')
        documents = loader.load()
        logging.info("[KnowledgeBase] Шаг 1: Файл успешно загружен.")

        logging.info("[KnowledgeBase] Шаг 2: Разделение текста на чанки...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)
        logging.info(f"[KnowledgeBase] Шаг 2: Текст разделен на {len(docs)} чанков.")

        logging.info("[KnowledgeBase] Шаг 3: Создание эмбеддингов и векторной базы...")
        embeddings = OpenAIEmbeddings(openai_api_key=api_key, base_url=base_url)
        vector_store = FAISS.from_documents(docs, embeddings)
        logging.info("[KnowledgeBase] Шаг 3: Векторная база успешно создана.")
        
        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
        logging.info("[KnowledgeBase] RAG-система успешно инициализирована.")

    except FileNotFoundError:
        logging.error("[KnowledgeBase] КРИТИЧЕСКАЯ ОШИБКА: Файл knowledge_base.txt не найден.")
        return None
    except Exception as e:
        logging.error(f"[KnowledgeBase] КРИТИЧЕСКАЯ ОШИБКА при инициализации: {e}", exc_info=True)
        return None

    def search_knowledge_base(query: str) -> str:
        """Ищет релевантную информацию в базе знаний по запросу пользователя."""
        try:
            relevant_docs = retriever.invoke(query)
            context = "\n\n".join([doc.page_content for doc in relevant_docs])
            logging.info(f"[KnowledgeBase] Найдена информация для запроса: '{query}'")
            return context
        except Exception as e:
            logging.error(f"[KnowledgeBase] Ошибка при поиске: {e}", exc_info=True)
            return "Произошла ошибка при поиске в базе знаний."

    return Tool(
        name="KnowledgeBaseSearch",
        func=search_knowledge_base,
        description="Всегда используй этот инструмент для поиска ответов на любые вопросы о продукте, его характеристиках, функциях, проблемах, доставке или возвратах. Передавай в него исходный вопрос пользователя без изменений."
    )

# --- Инструменты для Wildberries ---

_WB_ID_TO_TYPE_CACHE = {}

def get_unanswered_feedbacks_tool(date_provider=None):
    """
    Инструмент для получения неотвеченных отзывов.
    :param date_provider: Опциональная функция без аргументов, возвращающая объект datetime.
                          Если предоставлена, будут запрошены отзывы только после этой даты.
    """
    def run_tool(query: str = "") -> str:
        """Запускает получение отзывов."""
        logging.info("[WBTools] Вызван инструмент для получения неотвеченных отзывов.")
        
        date_from = None
        if date_provider:
            date_from = date_provider()
            logging.info(f"[WBTools] Используется фильтр по дате: {date_from.isoformat()}")

        feedbacks = get_unanswered_feedbacks(date_from=date_from) or []
        questions = get_unanswered_questions(date_from=date_from) or []

        # Пометим тип, чтобы агент мог различать, если нужно
        for f in feedbacks:
            f.setdefault("type", "feedback")
        for q in questions:
            q.setdefault("type", "question")
            # Приведём к общему виду поля текста, если отличается
            if "text" not in q and "questionText" in q:
                q["text"] = q.get("questionText", "")

        items = feedbacks + questions
        # Кэшируем типы для последующей отправки
        try:
            for it in items:
                _WB_ID_TO_TYPE_CACHE[it.get("id")] = it.get("type")
        except Exception:
            pass

        if feedbacks is None and questions is None:
            return "Не удалось получить отзывы. Возможно, проблема с API ключом или сетью."
        
        if not items:
            return "Новых неотвеченных отзывов и вопросов нет."
            
        return json.dumps(items, ensure_ascii=False, indent=2)

    return Tool(
        name="GetUnansweredFeedbacks",
        func=run_tool,
        description="Используй этот инструмент, чтобы проверить, есть ли на Wildberries новые неотвеченные вопросы или отзывы от покупателей. Инструмент не требует входных данных."
    )

def post_feedback_answer_tool():
    """Инструмент для отправки ответа на отзыв."""
    def run_tool(input_str: str) -> str:
        """Принимает JSON-строку с 'feedback_id' и 'text'."""
        try:
            logging.info(f"[WBTools] Вызван инструмент для отправки ответа. Сырой вход: {input_str}")
            
            # ИСПРАВЛЕНО: Убираем лишние кавычки/кодовые блоки, которые может добавить агент
            cleaned_input = input_str.strip().strip("''\"\"")
            cleaned_input = cleaned_input.strip('`').replace('\n', ' ').strip()
            logging.info(f"[WBTools] После предварительной очистки: {cleaned_input}")

            def parse_payload(s: str):
                # 1) Прямая попытка JSON
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
                # 2) Вырезаем первую фигурную скобку до последней закрывающей
                try:
                    start = s.find('{')
                    end = s.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        candidate = s[start:end+1]
                        return json.loads(candidate)
                except Exception:
                    pass
                # 3) Пытаемся распарсить как python-литерал и привести к dict
                try:
                    obj = ast.literal_eval(s)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
                raise json.JSONDecodeError("could not parse", s, 0)

            data = parse_payload(cleaned_input)
            feedback_id = data.get("feedback_id")
            text = data.get("text")
            item_type = data.get("type")  # feedback | question | None
            if not item_type:
                # Попробуем определить тип из кэша по id
                item_type = _WB_ID_TO_TYPE_CACHE.get(feedback_id)
            logging.info(
                f"[WBTools] Подготовка ответа: id={feedback_id}, type={item_type}, text_len={(len(text) if isinstance(text, str) else 'n/a')}"
            )
            
            if not feedback_id or not text:
                return "Ошибка: в запросе должны быть 'feedback_id' и 'text'."

            result = post_feedback_answer(feedback_id, text, item_type=item_type)
            
            if result is None:
                return f"Не удалось отправить ответ на отзыв/вопрос {feedback_id}. Проверяйте логи [WildberriesAPI]."
            
            return f"Ответ отправлен ({item_type or 'auto'}): {feedback_id}."

        except json.JSONDecodeError:
            return "Ошибка: Неверный формат JSON. Ожидается объект с ключами 'feedback_id' и 'text'."
        except Exception as e:
            logging.error(f"[WBTools] Неожиданная ошибка в инструменте отправки ответа: {e}", exc_info=True)
            return f"Произошла внутренняя ошибка при отправке ответа."

    return Tool(
        name="PostFeedbackAnswer",
        func=run_tool,
        description="Используй этот инструмент, чтобы отправить ответ на конкретный вопрос или отзыв. На вход нужно подать JSON-строку с двумя ключами: 'feedback_id' (уникальный идентификатор отзыва/вопроса) и 'text' (текст твоего ответа)."
    )
