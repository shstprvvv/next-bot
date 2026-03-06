import logging
import aiohttp
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class OzonClient:
    """
    Адаптер для работы с Ozon Seller API.
    Позволяет получать вопросы, отзывы и чаты, а также отправлять на них ответы.
    """
    def __init__(self, client_id: str, api_key: str):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = "https://api-seller.ozon.ru"
        self.headers = {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    async def _make_request(self, method: str, endpoint: str, json_data: dict = None) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}{endpoint}"
        try:
            # Отключаем проверку SSL сертификата (verify_ssl=False), так как на некоторых 
            # машинах Python (особенно на Mac) может не иметь корневых сертификатов Минцифры
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.request(method, url, headers=self.headers, json=json_data) as response:
                    if response.status in (200, 201):
                        return await response.json()
                    else:
                        text = await response.text()
                        logger.error(f"[OzonClient] Ошибка API {response.status} на {endpoint}: {text}")
                        return None
        except Exception as e:
            logger.error(f"[OzonClient] Исключение при запросе {endpoint}: {e}")
            return None

    # --- ВОПРОСЫ (Q&A) ---
    
    async def get_unanswered_questions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получает список вопросов покупателей, на которые еще нет ответа.
        В документации Ozon v1/question/list
        """
        # status: NEW - вопросы без ответа
        payload = {
            "filter": {
                "status": "NEW"
            },
            "limit": limit,
            "last_id": ""
        }
        
        # Ozon не так давно ввел отдельный API для вопросов и отзывов (interactive).
        # Эндпоинты могут отличаться, используем стандартные методы, если они недоступны - 
        # нужно проверить актуальную доку на docs.ozon.ru/api/seller
        endpoint = "/v1/question/list"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        if not response or "result" not in response:
            return []
            
        return response["result"].get("questions", [])

    async def answer_question(self, question_id: str, text: str) -> bool:
        """
        Отвечает на вопрос покупателя.
        """
        payload = {
            "question_id": question_id,
            "text": text
        }
        endpoint = "/v1/question/answer"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        # Обычно успешный ответ возвращает пустое тело или result: true
        if response is not None:
            return True
        return False
