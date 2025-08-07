# wildberries_api.py

import os
import requests
import logging
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any

load_dotenv()

# Загружаем токен из переменных окружения
WB_API_KEY = os.getenv('WB_API_KEY')
if not WB_API_KEY:
    logging.warning("[WildberriesAPI] Токен WB_API_KEY не найден в .env файле. Функции API Wildberries не будут работать.")

BASE_URL = "https://feedbacks-api.wildberries.ru/api/v1"
# ИСПРАВЛЕНО: Добавлен префикс "Bearer " к токену
HEADERS = {
    'Authorization': f'Bearer {WB_API_KEY}'
}

def get_unanswered_feedbacks(max_items: int = 20, date_from=None) -> Optional[list]:
    """
    Получает список неотвеченных отзывов и вопросов, начиная с определенной даты.
    """
    if not WB_API_KEY:
        logging.error("[WildberriesAPI] API-ключ Wildberries не установлен.")
        return None

    params = {
        "isAnswered": "false",
        "take": max_items,
        "skip": 0,
        "order": "dateAsc"
    }
    # Добавляем фильтр по дате, если он передан
    if date_from:
        params['dateFrom'] = int(date_from.timestamp())
        
    try:
        response = requests.get(f"{BASE_URL}/feedbacks", headers=HEADERS, params=params)
        response.raise_for_status()
        logging.info(f"[WildberriesAPI] Запрос неотвеченных отзывов: {response.status_code}")
        data = response.json()
        return data.get('data', {}).get('feedbacks', [])
    except requests.exceptions.RequestException as e:
        error_details = ""
        if e.response is not None:
            try:
                error_details = e.response.json()
            except json.JSONDecodeError:
                error_details = e.response.text
        logging.error(f"[WildberriesAPI] Ошибка при получении отзывов: {e}. Детали: {error_details}")
        return None

def get_unanswered_questions(max_items: int = 20, date_from=None) -> Optional[list]:
    """Получает список неотвеченных вопросов покупателей."""
    if not WB_API_KEY:
        logging.error("[WildberriesAPI] API-ключ Wildberries не установлен.")
        return None

    params = {
        "isAnswered": "false",
        "take": max_items,
        "skip": 0,
        "order": "dateAsc",
    }
    if date_from:
        params['dateFrom'] = int(date_from.timestamp())

    try:
        response = requests.get(f"{BASE_URL}/questions", headers=HEADERS, params=params)
        response.raise_for_status()
        logging.info(f"[WildberriesAPI] Запрос неотвеченных вопросов: {response.status_code}")
        data = response.json()
        return data.get('data', {}).get('questions', [])
    except requests.exceptions.RequestException as e:
        error_details = ""
        if e.response is not None:
            try:
                error_details = e.response.json()
            except json.JSONDecodeError:
                error_details = e.response.text
        logging.error(f"[WildberriesAPI] Ошибка при получении вопросов: {e}. Детали: {error_details}")
        return None

def post_feedback_answer(feedback_id: str, text: str, item_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Отправляет ответ на отзыв или вопрос.
    Если item_type == 'question' → использует /questions/answer, иначе /feedbacks/answer.
    При item_type=None сначала пробует отзыв, при неуспехе пробует вопрос.
    """
    if not WB_API_KEY:
        logging.error("[WildberriesAPI] API-ключ Wildberries не установлен.")
        return None

    body = {
        "id": feedback_id,
        "text": text
    }
    def _post(url_suffix: str, log_label: str):
        try:
            response = requests.post(f"{BASE_URL}/{url_suffix}", headers=HEADERS, json=body)
            response.raise_for_status()
            logging.info(f"[WildberriesAPI] Отправка ответа на {log_label} {feedback_id}: {response.status_code}")
            if response.status_code == 204:
                return {"result": "success"}
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if e.response is not None:
                try:
                    error_details = e.response.json()
                except json.JSONDecodeError:
                    error_details = e.response.text
            logging.error(f"[WildberriesAPI] Ошибка при отправке ответа на {log_label} {feedback_id}: {e}. Детали: {error_details}")
            return None

    # Явно задан тип вопроса
    if item_type == 'question':
        return _post("questions/answer", "вопрос")

    # По умолчанию пробуем как отзыв
    result = _post("feedbacks/answer", "отзыв")
    if result is None and item_type is None:
        # Фолбэк: пробуем как вопрос
        fallback = _post("questions/answer", "вопрос (fallback)")
        return fallback
    return result
