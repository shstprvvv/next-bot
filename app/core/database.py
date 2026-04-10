import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

DATABASE_PATH = os.getenv("DATABASE_PATH", "sessions/smart_bot.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    client_id = Column(String, nullable=True, index=True)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    bots = relationship("UserBot", back_populates="owner")


class UserBot(Base):
    __tablename__ = "user_bots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    assistant_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="bots")
    # Убираем проблемную связь, так как bot_id в KnowledgeFile это String, а id в UserBot это Integer
    # files = relationship("KnowledgeFile", back_populates="bot")


class KnowledgeFile(Base):
    """Таблица для хранения информации о загруженных файлах базы знаний"""
    __tablename__ = "knowledge_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bot_id = Column(String, nullable=False, index=True) # ID бота (из BOTS_REGISTRY или assistant_id)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False) # pdf, xlsx, txt и т.д.
    chunks_count = Column(Integer, default=0) # Сколько кусочков текста получилось
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User")
    # Убираем проблемную связь, так как bot_id может ссылаться на разные типы ботов
    # bot = relationship("UserBot", foreign_keys=[bot_id], primaryjoin="KnowledgeFile.bot_id == UserBot.assistant_id", viewonly=True)


def init_db():
    """Create tables if they don't exist (fallback when Alembic is not used)."""
    Base.metadata.create_all(bind=engine)

init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
