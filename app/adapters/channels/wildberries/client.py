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

    async def send_answer(self, id: str, text: str) -> bool:
        """
        Отправляет ответ на вопрос (или отзыв).
        POST /feedbacks/answer
        """
        payload = {
            "id": id,
            "text": text
        }
        
        async with httpx.AsyncClient() as client:
            try:
                # В документации WB метод ответа универсален для отзывов и вопросов
                response = await client.post(
                    f"{self.BASE_URL}/feedbacks/answer", 
                    headers=self.headers, 
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                logger.info(f"[WBClient] Ответ на {id} успешно отправлен.")
                return True
                
            except httpx.HTTPStatusError as e:
                logger.error(f"[WBClient] Ошибка при отправке ответа {id}: {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"[WBClient] Ошибка сети при ответе: {e}")
                return False
