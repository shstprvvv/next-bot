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

    # --- ЧАТЫ (Chats) ---

    async def get_unanswered_chats(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получает список чатов с непрочитанными сообщениями от покупателей.
        Используется эндпоинт v3/chat/list
        """
        payload = {
            "filter": {"chat_status": "Opened"},
            "limit": limit,
            "offset": 0
        }
        
        endpoint = "/v3/chat/list"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        if not response or "chats" not in response:
            return []
            
        chats = response.get("chats", [])
        # Фильтруем только чаты с покупателями, где есть непрочитанные сообщения
        unanswered_chats = [
            chat for chat in chats 
            if chat.get("unread_count", 0) > 0 and chat.get("chat", {}).get("chat_type") == "BUYER_SELLER"
        ]
        
        return unanswered_chats

    async def get_chat_history(self, chat_id: str, limit: int = 50) -> Optional[Dict[str, Any]]:
        """
        Получает историю сообщений в чате.
        Используется эндпоинт v3/chat/history
        """
        payload = {
            "chat_id": chat_id,
            "limit": limit,
            "direction": "Backward"
        }
        
        endpoint = "/v3/chat/history"
        
        return await self._make_request("POST", endpoint, json_data=payload)

    async def send_chat_message(self, chat_id: str, text: str) -> bool:
        """
        Отправляет сообщение в чат покупателю.
        Используется эндпоинт v1/chat/send/message
        """
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        
        endpoint = "/v1/chat/send/message"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        # Обычно успешный ответ возвращает строку (message_id) или объект
        if response is not None:
            return True
        return False

    async def mark_chat_read(self, chat_id: str, message_id: str) -> bool:
        """
        Помечает сообщения в чате как прочитанные до указанного message_id включительно.
        Используется эндпоинт v2/chat/read
        """
        payload = {
            "chat_id": chat_id,
            "from_message_id": str(message_id)
        }
        
        endpoint = "/v2/chat/read"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        if response is not None:
            return True
        return False
    # --- ОТЗЫВЫ (Reviews) ---

    async def get_unanswered_reviews(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получает список отзывов покупателей, на которые еще нет ответа.
        В документации Ozon v1/review/list
        """
        payload = {
            "with_interaction_status": [
                "UNVIEWED",
                "UNANSWERED"
            ],
            "limit": min(limit, 100), # Максимум 100 по документации
            "sort_dir": "DESC"
        }
        
        endpoint = "/v1/review/list"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        if not response or "reviews" not in response:
            return []
            
        return response.get("reviews", [])

    async def answer_review(self, review_id: str, text: str) -> bool:
        """
        Отвечает на отзыв покупателя.
        Используется эндпоинт v1/review/comment/create
        """
        payload = {
            "review_id": review_id,
            "text": text
        }
            
        endpoint = "/v1/review/comment/create"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        if response is not None and "comment_id" in response:
            return True
        return False
    
    async def get_unanswered_questions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получает список вопросов покупателей, на которые еще нет ответа.
        В документации Ozon v1/question/list
        """
        # status: NEW - новые вопросы.
        # Если NEW не возвращает вопросы, которые мы ожидаем, мы запрашиваем UNANSWERED или просто все
        payload = {
            "filter": {
                "status": "NEW"
            },
            "limit": limit,
            "last_id": ""
        }
        
        endpoint = "/v1/question/list"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        if not response or "questions" not in response:
            return []
            
        return response.get("questions", [])

    async def answer_question(self, question_id: str, text: str, sku: int = None) -> bool:
        """
        Отвечает на вопрос покупателя.
        """
        payload = {
            "question_id": question_id,
            "text": text
        }
        if sku is not None:
            payload["sku"] = sku
            
        endpoint = "/v1/question/answer/create"
        
        response = await self._make_request("POST", endpoint, json_data=payload)
        
        # Обычно успешный ответ возвращает пустое тело или result: true
        if response is not None:
            return True
        return False
