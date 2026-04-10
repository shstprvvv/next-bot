"""
Скрипт для создания аккаунта клиента NEXT в базе данных.
Запуск: python scripts/seed_next_client.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, User, init_db
from app.core.auth import get_password_hash

NEXT_EMAIL = "next@nextgadget.ru"
NEXT_PASSWORD = "NextAdmin2025!"
NEXT_CLIENT_ID = "next"
NEXT_DISPLAY_NAME = "NEXT Smart TV"


def seed():
    init_db()
    db = SessionLocal()

    try:
        existing = db.query(User).filter(User.email == NEXT_EMAIL).first()
        if existing:
            existing.client_id = NEXT_CLIENT_ID
            existing.display_name = NEXT_DISPLAY_NAME
            db.commit()
            print(f"[OK] Пользователь {NEXT_EMAIL} уже существует. Обновлен client_id={NEXT_CLIENT_ID}")
        else:
            user = User(
                email=NEXT_EMAIL,
                hashed_password=get_password_hash(NEXT_PASSWORD),
                client_id=NEXT_CLIENT_ID,
                display_name=NEXT_DISPLAY_NAME,
            )
            db.add(user)
            db.commit()
            print(f"[OK] Создан пользователь:")
            print(f"     Email:    {NEXT_EMAIL}")
            print(f"     Пароль:   {NEXT_PASSWORD}")
            print(f"     Client:   {NEXT_CLIENT_ID}")
            print(f"     Имя:      {NEXT_DISPLAY_NAME}")

        print()
        print("Для входа в админку:")
        print(f"  http://localhost:8080/static/login.html")
        print(f"  Email:  {NEXT_EMAIL}")
        print(f"  Пароль: {NEXT_PASSWORD}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
