import logging
import httpx
import time
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

    async def get_unanswered_questions(self, take: int = 10, skip: int = 0, date_from: Optional[datetime] = None) -> List[Dict[str, Any]]:
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
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/questions", 
                    headers=self.headers, 
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                # Структура ответа: {"data": {"questions": [...]}}
                questions = data.get("data", {}).get("questions", [])
                
                if questions:
                    logger.info(f"[WBClient] Получено {len(questions)} вопросов (с {date_from if date_from else 'начала времен'}).")
                
                return questions
                
            except httpx.HTTPStatusError as e:
                logger.error(f"[WBClient] Ошибка API {e.response.status_code}: {e.response.text}")
                return []
            except Exception as e:
                logger.error(f"[WBClient] Ошибка сети: {e}")
                return []

    async def get_unanswered_feedbacks(self, take: int = 10, skip: int = 0, date_from: Optional[datetime] = None) -> List[Dict[str, Any]]:
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
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/feedbacks", 
                    headers=self.headers, 
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                # Структура ответа: {"data": {"feedbacks": [...]}}
                feedbacks = data.get("data", {}).get("feedbacks", [])
                
                if feedbacks:
                    logger.info(f"[WBClient] Получено {len(feedbacks)} отзывов.")
                    
                return feedbacks
                
            except httpx.HTTPStatusError as e:
                logger.error(f"[WBClient] Ошибка API (feedbacks) {e.response.status_code}: {e.response.text}")
                return []
            except Exception as e:
                logger.error(f"[WBClient] Ошибка сети (feedbacks): {e}")
                return []

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
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.patch(
                    f"{self.BASE_URL}/questions", 
                    headers=self.headers, 
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"[WBClient] Ответ на вопрос {id} успешно отправлен.")
                return True
                
            except httpx.HTTPStatusError as e:
                logger.error(f"[WBClient] Ошибка при отправке ответа на вопрос {id}: {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"[WBClient] Ошибка сети при ответе на вопрос: {e}")
                return False

    async def answer_feedback(self, id: str, text: str) -> bool:
        """
        Отправляет ответ на отзыв.
        POST /feedbacks/answer
        """
        payload = {
            "id": id,
            "text": text
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.BASE_URL}/feedbacks/answer", 
                    headers=self.headers, 
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"[WBClient] Ответ на отзыв {id} успешно отправлен.")
                return True
                
            except httpx.HTTPStatusError as e:
                logger.error(f"[WBClient] Ошибка при отправке ответа на отзыв {id}: {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"[WBClient] Ошибка сети при ответе на отзыв: {e}")
                return False

    async def send_answer(self, id: str, text: str) -> bool:
        """
        DEPRECATED: Используйте answer_question или answer_feedback
        """
        logger.warning("[WBClient] Deprecated method send_answer called. Using answer_feedback as fallback.")
        return await self.answer_feedback(id, text)
