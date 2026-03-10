import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.adapters.channels.ozon.client import OzonClient
from app.adapters.db.database_adapter import DatabaseAdapter
from app.core.domain.models.marketplace_message import MarketplaceMessage
from app.core.use_cases.answer_question import AnswerQuestionUseCase

logger = logging.getLogger(__name__)

class OzonChatWorker:
    def __init__(
        self,
        ozon_client: OzonClient,
        db_adapter: DatabaseAdapter,
        answer_use_case: AnswerQuestionUseCase,
        poll_interval: int = 60
    ):
        self.ozon_client = ozon_client
        self.db_adapter = db_adapter
        self.answer_use_case = answer_use_case
        self.poll_interval = poll_interval
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("[OzonWorker-Chat] Запуск фоновой проверки чатов Ozon...")
        
        while self.is_running:
            try:
                await self._process_chats()
            except Exception as e:
                logger.error(f"[OzonWorker-Chat] Ошибка в цикле проверки: {e}")
            
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self.is_running = False
        logger.info("[OzonWorker-Chat] Остановка...")

    async def _process_chats(self):
        chats_data = await self.ozon_client.get_unanswered_chats()
        if not chats_data:
            return
            
        processed_count = 0
        
        for chat_info in chats_data:
            chat = chat_info.get("chat", {})
            chat_id = chat.get("chat_id")
            
            if not chat_id:
                continue
                
            # Получаем историю чата
            unread_count = chat_info.get("unread_count", 1)
            history = await self.ozon_client.get_chat_history(chat_id, limit=unread_count + 5)
            if not history or not history.get("messages"):
                continue
                
            messages = history["messages"]
            
            # Собираем все непрочитанные сообщения от покупателя
            customer_messages = []
            last_msg_id = None
            order_number = ""
            
            for msg in messages:
                if not msg.get("is_read", True) and msg.get("user", {}).get("type") == "Customer":
                    # Извлекаем текст
                    data = msg.get("data", [])
                    if data:
                        text = data[-1] if isinstance(data, list) else str(data)
                        customer_messages.append(text)
                        
                    if not last_msg_id:
                        last_msg_id = str(msg.get("message_id"))
                        
                    if not order_number:
                        order_number = msg.get("context", {}).get("order_number", "")
            
            if not customer_messages or not last_msg_id:
                continue
                
            # Сообщения идут от новых к старым, поэтому переворачиваем для правильного порядка
            customer_messages.reverse()
            msg_text = "\n".join(customer_messages)
            
            # Проверяем, обрабатывали ли мы это сообщение (по ID последнего сообщения)
            db_id = f"ozon_chat_{chat_id}_{last_msg_id}"
            existing_msg = self.db_adapter.get_message(db_id)
            
            if existing_msg and existing_msg.status in ("processing", "answered"):
                continue
                
            logger.info(f"[OzonWorker-Chat] Новое сообщение в чате {chat_id} (Заказ: {order_number}): {msg_text[:50]}...")
            
            # Сохраняем в БД со статусом processing
            message_record = MarketplaceMessage(
                id=db_id,
                marketplace="ozon",
                message_type="chat",
                item_id=chat_id,
                product_name=f"Заказ {order_number}" if order_number else "Чат",
                text=msg_text,
                status="processing",
                created_at=datetime.now()
            )
            self.db_adapter.save_message(message_record)
            
            # Генерируем ответ
            try:
                # Используем AnswerQuestionUseCase, так как он подходит для чатов
                # Убираем context, так как AnswerQuestionUseCase.execute принимает только text
                answer_text = await self.answer_use_case.execute(question=msg_text)
                
                if answer_text:
                    # Отправляем ответ
                    success = await self.ozon_client.send_chat_message(chat_id, answer_text)
                    
                    if success:
                        logger.info(f"[OzonWorker-Chat] Успешно отправлен ответ в чат {chat_id}")
                        
                        # Помечаем сообщения как прочитанные
                        await self.ozon_client.mark_chat_read(chat_id, last_msg_id)
                        
                        message_record.status = "answered"
                        message_record.answer_text = answer_text
                        message_record.answered_at = datetime.now()
                        self.db_adapter.save_message(message_record)
                        processed_count += 1
                    else:
                        logger.error(f"[OzonWorker-Chat] Ошибка при отправке ответа в чат {chat_id}")
                        message_record.status = "failed"
                        self.db_adapter.save_message(message_record)
                else:
                    logger.warning(f"[OzonWorker-Chat] Не удалось сгенерировать ответ для чата {chat_id}")
                    message_record.status = "failed"
                    self.db_adapter.save_message(message_record)
                    
            except Exception as e:
                logger.error(f"[OzonWorker-Chat] Ошибка при обработке чата {chat_id}: {e}")
                message_record.status = "failed"
                self.db_adapter.save_message(message_record)
                
        if processed_count > 0:
            logger.info(f"[OzonWorker-Chat] Обработано {processed_count} новых сообщений.")
