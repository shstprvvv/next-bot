import logging
import asyncio
import httpx
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class WBClient:
    """
    Асинхронный клиент для Wildberries API (Feedbacks & Questions).
    """
    BASE_URL = "https://feedbacks-api.wildberries.ru/api/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(10.0, connect=5.0, read=10.0, write=10.0, pool=10.0)
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
            self._client = httpx.AsyncClient(timeout=timeout, limits=limits)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        max_attempts: int = 4,
    ) -> Optional[dict]:
        client = self._get_client()
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await client.request(
                    method,
                    url,
                    headers=self.headers,
                    params=params,
                    json=json,
                )

                # ретраи на 429/5xx
                if resp.status_code == 429 or 500 <= resp.status_code <= 599:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after is not None else None
                    except ValueError:
                        delay = None
                    if delay is None:
                        delay = min(10.0, 0.5 * (2 ** (attempt - 1)))
                    logger.warning(
                        f"[WBClient] {method} {url} -> {resp.status_code}. Retry in {delay:.1f}s (attempt {attempt}/{max_attempts})"
                    )
                    await resp.aclose()
                    if attempt >= max_attempts:
                        logger.error(f"[WBClient] Исчерпаны ретраи: {resp.status_code}: {resp.text}")
                        return None
                    await asyncio.sleep(delay)
                    continue

                resp.raise_for_status()
                
                # Если 204 No Content, возвращаем пустой словарь, чтобы отличить от ошибки (None)
                if resp.status_code == 204:
                    await resp.aclose()
                    return {}
                    
                try:
                    data = resp.json()
                except ValueError:
                    # Если ответ не содержит JSON (например, пустой или текст), но status_code успешный (2xx)
                    # то просто вернем пустой словарь или текст, чтобы не было ошибки None
                    data = {"text_response": resp.text} if resp.text else {}
                    
                await resp.aclose()
                return data

            except httpx.HTTPStatusError as e:
                # 4xx (кроме 429) — обычно не ретраим
                logger.error(f"[WBClient] Ошибка API {e.response.status_code}: {e.response.text}")
                try:
                    await e.response.aclose()
                except Exception:
                    pass
                return None
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                delay = min(10.0, 0.5 * (2 ** (attempt - 1)))
                logger.warning(
                    f"[WBClient] Сетевая ошибка {method} {url}: {e}. Retry in {delay:.1f}s (attempt {attempt}/{max_attempts})"
                )
                if attempt >= max_attempts:
                    logger.error(f"[WBClient] Исчерпаны ретраи по сети: {e}", exc_info=True)
                    return None
                await asyncio.sleep(delay)
            except Exception as e:
                last_exc = e
                logger.error(f"[WBClient] Неожиданная ошибка запроса: {e}", exc_info=True)
                return None

        if last_exc is not None:
            logger.error(f"[WBClient] Запрос завершился ошибкой: {last_exc}", exc_info=True)
        return None

    async def get_unanswered_questions(self, take: int = 5000, skip: int = 0, date_from: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Получает список неотвеченных вопросов.
        GET /questions?isAnswered=false
        """
        params = {
            "isAnswered": "false",
            "take": take,
            "skip": skip,
            "order": "dateAsc"
        }
        
        if date_from:
            # WB API ожидает unix timestamp (секунды)
            params["dateFrom"] = int(date_from.timestamp())

        data = await self._request_json("GET", f"{self.BASE_URL}/questions", params=params)
        if not data:
            return []

        questions = data.get("data", {}).get("questions", [])
        if questions:
            logger.info(f"[WBClient] Получено {len(questions)} вопросов (с {date_from if date_from else 'начала времен'}).")
        return questions

    async def get_unanswered_feedbacks(self, take: int = 5000, skip: int = 0, date_from: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Получает список неотвеченных отзывов.
        GET /feedbacks?isAnswered=false
        """
        params = {
            "isAnswered": "false",
            "take": take,
            "skip": skip,
            "order": "dateAsc"
        }
        
        if date_from:
            params["dateFrom"] = int(date_from.timestamp())

        data = await self._request_json("GET", f"{self.BASE_URL}/feedbacks", params=params)
        if not data:
            return []

        feedbacks = data.get("data", {}).get("feedbacks", [])
        if feedbacks:
            logger.info(f"[WBClient] Получено {len(feedbacks)} отзывов.")
        return feedbacks

    async def answer_question(self, id: str, text: str) -> bool:
        """
        Отправляет ответ на вопрос.
        PATCH /questions
        """
        payload = {
            "id": id,
            "answer": {
                "text": text
            },
            "state": "wbRu"
        }

        data = await self._request_json("PATCH", f"{self.BASE_URL}/questions", json=payload)
        if data is None:
            logger.error(f"[WBClient] Не удалось отправить ответ на вопрос {id}.")
            return False
        logger.info(f"[WBClient] Ответ на вопрос {id} успешно отправлен.")
        return True

    async def answer_feedback(self, id: str, text: str) -> bool:
        """
        Отправляет ответ на отзыв.
        PATCH /api/v1/feedbacks
        """
        payload = {
            "id": id,
            "text": text
        }
        logger.info(f"[WBClient] Отправка PATCH-запроса на /feedbacks/answer для отзыва {id}. Payload: {payload}")

        # Ранее мы получали 405 Method Not Allowed на PATCH /feedbacks, так что меняем на PATCH /feedbacks/answer,
        # так как POST возвращает 405 Method Not Allowed
        data = await self._request_json("PATCH", f"{self.BASE_URL}/feedbacks/answer", json=payload)
        
        # Если PATCH не работает, попробуем POST, но с правильным Content-Type (он уже задан в заголовках)
        if data is None:
            logger.info(f"[WBClient] PATCH-запрос не удался. Пробую POST на /feedbacks/answer для отзыва {id}.")
            data = await self._request_json("POST", f"{self.BASE_URL}/feedbacks/answer", json=payload)
        
        if data is None:
            logger.error(f"[WBClient] Не удалось отправить ответ на отзыв {id}. Data is None.")
            return False
            
        logger.info(f"[WBClient] Ответ на отзыв {id} успешно отправлен. Response data: {data}")
        return True

    async def send_answer(self, id: str, text: str) -> bool:
        """
        DEPRECATED: Используйте answer_question или answer_feedback
        """
        logger.warning("[WBClient] Deprecated method send_answer called. Using answer_feedback as fallback.")
        return await self.answer_feedback(id, text)

    # --- Chat API ---

    async def get_chat_events(self, next_token: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Получает события чатов (инкрементально).
        GET /api/v1/seller/events
        """
        url = "https://buyer-chat-api.wildberries.ru/api/v1/seller/events"
        params = {}
        if next_token is not None:
            params["next"] = next_token
        
        data = await self._request_json("GET", url, params=params)
        return data

    async def send_chat_message(self, chat_id: str, text: str, reply_sign: str) -> bool:
        """
        Отправляет сообщение в чат с покупателем.
        """
        url = "https://buyer-chat-api.wildberries.ru/api/v1/seller/message"
        
        # По документации ожидается multipart/form-data. Но мы можем отправить и JSON.
        # Формируем тело так, чтобы покрыть возможные варианты API.
        payload = {
            "chatId": chat_id,
            "chatID": chat_id,
            "text": text,
            "message": text,
            "replySign": reply_sign
        }
        
        data = await self._request_json("POST", url, json=payload)
        
        if data is None:
            logger.error(f"[WBClient] Не удалось отправить сообщение в чат {chat_id}.")
            return False
            
        logger.info(f"[WBClient] Сообщение в чат {chat_id} успешно отправлено.")
        return True

    async def download_chat_file(self, download_id: str) -> Optional[bytes]:
        """
        Скачивает файл (например, картинку) из чата по downloadID.
        """
        url = f"https://buyer-chat-api.wildberries.ru/api/v1/seller/download/{download_id}"
        
        client = self._get_client()
        try:
            resp = await client.request("GET", url, headers=self.headers)
            if resp.status_code == 200:
                return resp.content
            logger.error(f"[WBClient] Ошибка скачивания файла {download_id}: {resp.status_code}")
        except Exception as e:
            logger.error(f"[WBClient] Исключение при скачивании файла {download_id}: {e}", exc_info=True)
            
        return None
