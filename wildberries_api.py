# wildberries_api.py

import os
import json
import requests
import logging
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any

load_dotenv()

# Загружаем токен из переменных окружения
WB_API_KEY = os.getenv('WB_API_KEY')
if not WB_API_KEY:
    logging.warning("[WildberriesAPI] Токен WB_API_KEY не найден в .env файле. Функции API Wildberries не будут работать.")

# Базовый адрес API общения с покупателем (включает отзывы/вопросы и чат)
BASE_URL = "https://feedbacks-api.wildberries.ru/api/v1"
# ИСПРАВЛЕНО: Добавлен префикс "Bearer " к токену
HEADERS = {
    'Authorization': f'Bearer {WB_API_KEY}',
    'Content-Type': 'application/json'
}


def _preview(value: Any, max_len: int = 300) -> str:
    try:
        s = str(value)
    except Exception:
        s = "<unprintable>"
    if len(s) > max_len:
        return s[:max_len] + "…"
    return s

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
    """Отправляет ответ на отзыв или вопрос (единый эндпоинт /feedbacks/answer)."""
    if not WB_API_KEY:
        logging.error("[WildberriesAPI] API-ключ Wildberries не установлен.")
        return None

    body = {
        "id": feedback_id,
        "text": text
    }
    def _post(url_suffix: str, log_label: str):
        try:
            logging.info(
                f"[WildberriesAPI] Подготовка запроса: url={BASE_URL}/{url_suffix}, id={feedback_id}, text_len={len(text)}"
            )
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

    # Всегда используем единый эндпоинт для публикации ответа (поддерживает вопросы и отзывы)
    return _post("feedbacks/answer", "элемент")

# --- ЧАТ С ПОКУПАТЕЛЕМ ---

def get_chat_events(last_event_id: Optional[int] = None, limit: int = 100) -> Optional[Dict[str, Any]]:
    """Получает события чатов продавца.

    Документация: см. "Чат с покупателями / События чатов".
    Эндпоинт: GET /seller/events

    Параметры:
    - last_event_id: обработанный последний ID события (для инкрементальной выборки)
    - limit: максимум событий за один запрос
    """
    if not WB_API_KEY:
        logging.error("[WildberriesAPI] API-ключ Wildberries не установлен.")
        return None

    params: Dict[str, Any] = {"limit": limit}
    if last_event_id is not None:
        # Параметр может называться lastEventId (в камеле) — подготовим оба варианта
        params["lastEventId"] = last_event_id
        params["last_event_id"] = last_event_id

    try:
        url = f"{BASE_URL}/seller/events"
        logging.info(f"[WildberriesAPI] Запрос событий чата: {url} params={params}")
        response = requests.get(url, headers=HEADERS, params=params)
        logging.info(f"[WildberriesAPI] События чата статус: {response.status_code}")
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError:
            text_preview = _preview(response.text)
            logging.error(f"[WildberriesAPI] Некорректный JSON в ответе событий. Тело: {text_preview}")
            return None
        events_count = 0
        try:
            events_count = len((data or {}).get('data', {}).get('events', []))
        except Exception:
            pass
        logging.info(f"[WildberriesAPI] Получено событий: {events_count}")
        return data
    except requests.exceptions.RequestException as e:
        error_details = ""
        if e.response is not None:
            try:
                error_details = e.response.json()
            except json.JSONDecodeError:
                error_details = e.response.text
        logging.error(f"[WildberriesAPI] Ошибка при получении событий чата: {e}. Детали: {error_details}")
        return None


def list_chats(limit: int = 50, offset: int = 0) -> Optional[Dict[str, Any]]:
    """Возвращает список чатов продавца.

    Эндпоинт: GET /seller/chats
    """
    if not WB_API_KEY:
        logging.error("[WildberriesAPI] API-ключ Wildberries не установлен.")
        return None

    params = {"limit": limit, "offset": offset}
    try:
        url = f"{BASE_URL}/seller/chats"
        logging.info(f"[WildberriesAPI] Запрос списка чатов: {url} params={params}")
        response = requests.get(url, headers=HEADERS, params=params)
        logging.info(f"[WildberriesAPI] Список чатов статус: {response.status_code}")
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError:
            text_preview = _preview(response.text)
            logging.error(f"[WildberriesAPI] Некорректный JSON списка чатов. Тело: {text_preview}")
            return None
        total = 0
        try:
            total = len((data or {}).get('data', {}).get('chats', []))
        except Exception:
            pass
        logging.info(f"[WildberriesAPI] Получено чатов: {total}")
        return data
    except requests.exceptions.RequestException as e:
        error_details = ""
        if e.response is not None:
            try:
                error_details = e.response.json()
            except json.JSONDecodeError:
                error_details = e.response.text
        logging.error(f"[WildberriesAPI] Ошибка при получении списка чатов: {e}. Детали: {error_details}")
        return None


def post_chat_message(chat_id: str, text: str) -> Optional[Dict[str, Any]]:
    """Отправляет сообщение в чат с покупателем.

    Эндпоинт: POST /seller/message
    Тело: { "chatId": string, "text": string }
    """
    if not WB_API_KEY:
        logging.error("[WildberriesAPI] API-ключ Wildberries не установлен.")
        return None

    payload = {"chatId": chat_id, "text": text}
    try:
        url = f"{BASE_URL}/seller/message"
        logging.info(
            f"[WildberriesAPI] Отправка сообщения в чат: chatId={chat_id}, text_preview={_preview(text, 120)}"
        )
        response = requests.post(url, headers=HEADERS, json=payload)
        logging.info(f"[WildberriesAPI] Ответ на отправку сообщения: {response.status_code}")
        response.raise_for_status()
        if response.status_code in (200, 201, 204):
            return {"result": "success"}
        try:
            return response.json()
        except json.JSONDecodeError:
            text_preview = _preview(response.text)
            logging.error(f"[WildberriesAPI] Некорректный JSON при отправке сообщения. Тело: {text_preview}")
            return None
    except requests.exceptions.RequestException as e:
        error_details = ""
        if e.response is not None:
            try:
                error_details = e.response.json()
            except json.JSONDecodeError:
                error_details = e.response.text
        logging.error(f"[WildberriesAPI] Ошибка при отправке сообщения в чат: {e}. Детали: {error_details}")
        return None
