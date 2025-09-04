import logging
import json
import ast
from langchain.tools import Tool
from app.wb.api import (
    get_unanswered_feedbacks,
    get_unanswered_questions,
    post_feedback_answer,
    get_chat_events,
    list_chats,
    post_chat_message,
)

_WB_ID_TO_TYPE_CACHE = {}


def get_unanswered_feedbacks_tool(date_provider=None):
    def run_tool(query: str = "") -> str:
        logging.info("[WBTools] Вызван инструмент для получения неотвеченных отзывов.")

        date_from = None
        if date_provider:
            date_from = date_provider()
            logging.info(f"[WBTools] Используется фильтр по дате: {date_from.isoformat()}")

        feedbacks = get_unanswered_feedbacks(date_from=date_from) or []
        questions = get_unanswered_questions(date_from=date_from) or []

        for f in feedbacks:
            f.setdefault("type", "feedback")
        for q in questions:
            q.setdefault("type", "question")
            if "text" not in q and "questionText" in q:
                q["text"] = q.get("questionText", "")

        items = feedbacks + questions
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
    def run_tool(input_str: str) -> str:
        try:
            logging.info(f"[WBTools] Вызван инструмент для отправки ответа. Сырой вход: {input_str}")

            cleaned_input = input_str.strip().strip("''\"\"")
            cleaned_input = cleaned_input.strip('`').replace('\n', ' ').strip()
            logging.info(f"[WBTools] После предварительной очистки: {cleaned_input}")

            def parse_payload(s: str):
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
                try:
                    start = s.find('{')
                    end = s.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        candidate = s[start:end+1]
                        return json.loads(candidate)
                except Exception:
                    pass
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
            item_type = data.get("type") or _WB_ID_TO_TYPE_CACHE.get(feedback_id)

            if not feedback_id or not text:
                return f"Ошибка: в JSON должны быть 'feedback_id' и 'text'. Получено: {cleaned_input}"

            logging.info(f"[WBTools] Подготовка ответа: id={feedback_id}, type={item_type}, text_len={len(text)}")

            # Используем безопасную версию текста, чтобы избежать проблем с API
            safe_text = text.strip()

            result = post_feedback_answer(feedback_id, safe_text, item_type=item_type)

            if result:
                return f"Ответ на отзыв/вопрос {feedback_id} успешно отправлен."

        except json.JSONDecodeError:
            return "Ошибка: Неверный формат JSON. Ожидается объект с ключами 'feedback_id' и 'text'."
        except Exception as e:
            logging.error(f"[WBTools] Неожиданная ошибка в инструменте отправки ответа: {e}", exc_info=True)
            return f"Произошла внутренняя ошибка при отправке ответа."

    return Tool(
        name="PostFeedbackAnswer",
        func=run_tool,
        description="Отправляет ответ на конкретный вопрос или отзыв. Вход: JSON-строка с 'feedback_id' и 'text'."
    )


def get_chat_events_tool():
    def run_tool(input_str: str) -> str:
        try:
            data = {}
            if input_str and input_str.strip():
                try:
                    data = json.loads(input_str)
                except Exception:
                    pass
            last_event_id = data.get("last_event_id")
            next_token = data.get("next")
            limit = data.get("limit", 100)
            logging.info(f"[WBTools] GetChatEvents last_event_id={last_event_id} next={next_token} limit={limit}")
            events = get_chat_events(last_event_id=last_event_id, next_token=next_token, limit=limit)
            if events is None:
                return "Не удалось получить события чатов."
            try:
                result = json.dumps(events, ensure_ascii=False)
            except Exception:
                result = str(events)
            logging.info(f"[WBTools] GetChatEvents ok, size={len(result)}")
            return result
        except Exception as e:
            logging.error(f"[WBTools] Ошибка get_chat_events_tool: {e}")
            return "Произошла ошибка при получении событий чатов."

    return Tool(
        name="GetChatEvents",
        func=run_tool,
        description="Получает события чатов продавца (инкрементально). На вход принимает JSON с полями last_event_id, next и limit."
    )


def post_chat_message_tool():
    def run_tool(input_str: str) -> str:
        try:
            data = json.loads(input_str)
            chat_id = data.get("chat_id")
            text = data.get("text")
            reply_sign = data.get("reply_sign")
            if not chat_id or not text:
                return "Ошибка: обязательны chat_id и text"
            logging.info(f"[WBTools] PostChatMessage chat_id={chat_id} text_len={len(text)} reply_sign={bool(reply_sign)}")
            result = post_chat_message(chat_id, text, reply_sign=reply_sign)
            if result is None:
                return "Не удалось отправить сообщение в чат."
            logging.info("[WBTools] PostChatMessage ok")
            return "Сообщение отправлено."
        except Exception as e:
            logging.error(f"[WBTools] Ошибка post_chat_message_tool: {e}")
            return "Произошла ошибка при отправке сообщения."

    return Tool(
        name="PostChatMessage",
        func=run_tool,
        description="Отправляет сообщение в чат покупателю. На вход JSON: chat_id, text, reply_sign (опционально)."
    )


