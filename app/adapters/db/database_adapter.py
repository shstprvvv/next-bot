import os
import sqlite3
import logging
from typing import Optional
from datetime import datetime
from app.core.domain.models.marketplace_message import MarketplaceMessage

logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "sessions/smart_bot.db")


class DatabaseAdapter:
    def __init__(self, db_path: str = DATABASE_PATH):
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

    def count_answered(self, category: str) -> int:
        """Подсчёт отвеченных сообщений по категории (wb_questions, wb_feedbacks, ozon_questions, ozon_reviews)"""
        mapping = {
            "wb_questions": ("wildberries", "question"),
            "wb_feedbacks": ("wildberries", "feedback"),
            "ozon_questions": ("ozon", "question"),
            "ozon_reviews": ("ozon", "review"),
        }
        if category not in mapping:
            return 0
        marketplace, msg_type = mapping[category]
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM marketplace_messages WHERE marketplace = ? AND message_type = ? AND status = 'answered'",
                    (marketplace, msg_type)
                )
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"[Database] Ошибка count_answered({category}): {e}")
            return 0

    def get_recent_messages(self, limit: int = 5) -> list:
        """Последние отвеченные сообщения для дашборда"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT marketplace, message_type, text, answer_text, answered_at
                       FROM marketplace_messages
                       WHERE status = 'answered' AND answer_text IS NOT NULL
                       ORDER BY answered_at DESC LIMIT ?""",
                    (limit,)
                )
                rows = cursor.fetchall()
                return [
                    {
                        "marketplace": r[0],
                        "type": r[1],
                        "question": r[2][:120] if r[2] else "",
                        "answer": r[3][:120] if r[3] else "",
                        "answered_at": r[4],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"[Database] Ошибка get_recent_messages: {e}")
            return []

    def get_daily_stats(self, days: int = 7) -> dict:
        """Статистика по дням за последние N дней"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT date(answered_at) as d, message_type, COUNT(*)
                       FROM marketplace_messages
                       WHERE status = 'answered' AND answered_at >= date('now', ?)
                       GROUP BY d, message_type
                       ORDER BY d ASC""",
                    (f'-{days} days',)
                )
                rows = cursor.fetchall()
                
                # Инициализация пустых данных за последние 7 дней
                from datetime import datetime, timedelta
                today = datetime.now()
                dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days-1, -1, -1)]
                
                stats = {
                    "dates": dates,
                    "questions": [0] * days,
                    "feedbacks": [0] * days,
                }
                
                for r in rows:
                    date_str, msg_type, count = r
                    if date_str in dates:
                        idx = dates.index(date_str)
                        if msg_type == 'question':
                            stats["questions"][idx] += count
                        elif msg_type in ('feedback', 'review'):
                            stats["feedbacks"][idx] += count
                            
                return stats
        except Exception as e:
            logger.error(f"[Database] Ошибка get_daily_stats: {e}")
            return {"dates": [], "questions": [], "feedbacks": []}

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
