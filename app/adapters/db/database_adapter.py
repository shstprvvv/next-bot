import sqlite3
import logging
from typing import Optional, List
from datetime import datetime
from app.core.domain.models.marketplace_message import MarketplaceMessage

logger = logging.getLogger(__name__)

class DatabaseAdapter:
    def __init__(self, db_path: str = "smart_bot.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS marketplace_messages (
                        id TEXT PRIMARY KEY,
                        marketplace TEXT NOT NULL,
                        message_type TEXT NOT NULL,
                        item_id TEXT NOT NULL,
                        product_name TEXT,
                        text TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        answer_text TEXT,
                        answered_at TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("[Database] Таблица marketplace_messages инициализирована.")
        except Exception as e:
            logger.error(f"[Database] Ошибка инициализации БД: {e}")

    def save_message(self, message: MarketplaceMessage) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO marketplace_messages 
                    (id, marketplace, message_type, item_id, product_name, text, status, created_at, answer_text, answered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message.id,
                    message.marketplace,
                    message.message_type,
                    message.item_id,
                    message.product_name,
                    message.text,
                    message.status,
                    message.created_at.isoformat() if message.created_at else None,
                    message.answer_text,
                    message.answered_at.isoformat() if message.answered_at else None
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[Database] Ошибка сохранения сообщения {message.id}: {e}")
            return False

    def get_message(self, message_id: str) -> Optional[MarketplaceMessage]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM marketplace_messages WHERE id = ?", (message_id,))
                row = cursor.fetchone()
                if row:
                    return MarketplaceMessage(
                        id=row[0],
                        marketplace=row[1],
                        message_type=row[2],
                        item_id=row[3],
                        product_name=row[4],
                        text=row[5],
                        status=row[6],
                        created_at=datetime.fromisoformat(row[7]) if row[7] else None,
                        answer_text=row[8],
                        answered_at=datetime.fromisoformat(row[9]) if row[9] else None
                    )
                return None
        except Exception as e:
            logger.error(f"[Database] Ошибка получения сообщения {message_id}: {e}")
            return None

    def update_status(self, message_id: str, status: str, answer_text: str = None) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                
                if answer_text is not None:
                    cursor.execute("""
                        UPDATE marketplace_messages 
                        SET status = ?, answer_text = ?, answered_at = ?
                        WHERE id = ?
                    """, (status, answer_text, now, message_id))
                else:
                    cursor.execute("""
                        UPDATE marketplace_messages 
                        SET status = ?
                        WHERE id = ?
                    """, (status, message_id))
                    
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[Database] Ошибка обновления статуса сообщения {message_id}: {e}")
            return False
