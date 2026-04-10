import os
import logging
import json
import traceback
import asyncio
from typing import List, Optional, Dict

import aiohttp
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import redis.asyncio as redis

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from sqlalchemy.orm import Session
from app.core.database import get_db, User, KnowledgeFile
from app.core.auth import get_password_hash, verify_password, create_access_token, decode_access_token
from fastapi.security import OAuth2PasswordBearer

from app.config import load_config
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.qdrant_adapter import QdrantRetrieverAdapter
from app.core.scenarios.universal_graph import UniversalScenarioGraph
from app.core.scenarios.onboarding.graph import OnboardingScenarioGraph
from app.adapters.openai_assistants.adapter import OpenAIAssistantsAdapter
from app.core.config.bots_registry import BOTS_REGISTRY
from app.core.knowledge_manager import KnowledgeManager
from telethon import TelegramClient
from telethon.sessions import MemorySession

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s")
logger = logging.getLogger("API")

load_dotenv()
cfg = load_config()

app = FastAPI(title="NextBot API", description="API для виджетов на сайтах (SaaS Architecture)")

limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.getenv("TESTING", "").lower() not in ("1", "true"),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logger.error(
        "Unhandled exception: %s %s -> %s\n%s",
        request.method,
        request.url.path,
        repr(exc),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"},
    )

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Глобальные переменные
# Теперь мы храним графы для всех ботов
scenario_graphs: Dict[str, UniversalScenarioGraph] = {}
onboarding_graph: Optional[OnboardingScenarioGraph] = None
assistants_adapter: Optional[OpenAIAssistantsAdapter] = None
knowledge_manager: Optional[KnowledgeManager] = None
llm_adapter: Optional[LangChainLLMAdapter] = None

# Подключение к Redis
# По умолчанию используем localhost, если не задано в .env
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None
SESSION_TTL_SECONDS = 20 * 60  # 20 минут

TESTING = os.getenv("TESTING", "").lower() in ("1", "true")


@app.on_event("startup")
async def startup_event():
    global scenario_graphs, redis_client, onboarding_graph, assistants_adapter, knowledge_manager, llm_adapter

    if TESTING:
        logger.info("Запуск в тестовом режиме — пропуск внешних сервисов")
        return

    logger.info("Инициализация API сервера и LangGraph для всех ботов...")

    try:
        _rc = redis.from_url(REDIS_URL, decode_responses=True)
        await _rc.ping()
        redis_client = _rc
        logger.info(f"Успешное подключение к Redis по адресу {REDIS_URL}")
    except Exception as e:
        redis_client = None
        logger.error(f"Ошибка подключения к Redis: {e}. Сессии будут работать без истории.")

    try:
        llm_adapter = LangChainLLMAdapter(
            api_key=cfg.get("OPENAI_API_KEY"),
            base_url=cfg.get("OPENAI_API_BASE"),
            model_name=cfg.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        )
        logger.info("LLM адаптер инициализирован.")

        assistants_adapter = OpenAIAssistantsAdapter(
            api_key=cfg.get("OPENAI_API_KEY"),
            base_url=cfg.get("OPENAI_API_BASE")
        )

        onboarding_graph = OnboardingScenarioGraph(llm_adapter, assistants_adapter)

        knowledge_manager = KnowledgeManager(
            openai_api_key=cfg.get("OPENAI_API_KEY"),
            openai_api_base=cfg.get("OPENAI_API_BASE")
        )
    except Exception as e:
        logger.error(f"Ошибка при инициализации LLM/Assistants: {e}")

    try:
        for bot_id, bot_config in BOTS_REGISTRY.items():
            logger.info(f"Инициализация бота: {bot_id} ({bot_config['name']})")

            retriever_adapter = QdrantRetrieverAdapter(
                collection_name=bot_config["collection_name"],
                knowledge_base_path=f"{bot_id}_kb.md",
                openai_api_key=cfg.get("OPENAI_API_KEY"),
                openai_api_base=cfg.get("OPENAI_API_BASE")
            )

            graph = UniversalScenarioGraph(llm_adapter, retriever_adapter, bot_config)
            scenario_graphs[bot_id] = graph

        logger.info(f"Успешно инициализировано ботов: {len(scenario_graphs)}")
    except Exception as e:
        logger.error(f"Ошибка при инициализации LangGraph (Qdrant): {e}. Чат будет работать в fallback-режиме.")

@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Подключение к Redis закрыто.")

class ChatRequest(BaseModel):
    bot_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field(..., min_length=1, max_length=128)

class ChatResponse(BaseModel):
    reply: str

class InitRequest(BaseModel):
    bot_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)

class AuthRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254, pattern=r'^[\w\.\+\-]+@[\w\-]+\.[\w\.\-]+$')
    password: str = Field(..., min_length=8, max_length=128)

@app.post("/api/auth/register")
@limiter.limit("5/minute")
async def register_user(request: Request, body: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(body.password)
    new_user = User(email=body.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(data={"sub": new_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login_user(request: Request, body: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(data={"sub": body.email})
    return {"access_token": access_token, "token_type": "bearer"}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    email: str = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_session_history(session_key: str) -> List[str]:
    """Получает историю сессии из Redis"""
    if not redis_client:
        return []

    data = await redis_client.get(session_key)
    if data:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return []
    return []

async def get_onboarding_state(session_key: str) -> dict:
    """Получает стейт онбординга из Redis"""
    if not redis_client:
        return {}

    data = await redis_client.get(f"state:{session_key}")
    if data:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {}
    return {}

async def save_session_history(session_key: str, history: List[str], state: dict = None):
    """Сохраняет историю сессии и стейт в Redis с TTL"""
    if not redis_client:
        return

    # Ограничиваем историю последними 20 сообщениями
    if len(history) > 20:
        history = history[-20:]

    await redis_client.setex(
        name=session_key,
        time=SESSION_TTL_SECONDS,
        value=json.dumps(history)
    )

    if state:
        await redis_client.setex(
            name=f"state:{session_key}",
            time=SESSION_TTL_SECONDS,
            value=json.dumps(state)
        )

@app.post("/api/chat/init", response_model=ChatResponse)
@limiter.limit("30/minute")
async def init_endpoint(request: Request, body: InitRequest, current_user: User = Depends(get_current_user)):
    """Инициализация чата. Создает сессию и возвращает приветствие."""
    bot_id = body.bot_id
    session_key = f"session:{bot_id}:{body.session_id}"

    # Специальная логика для Бота-Онбордера
    if bot_id == "creator_bot":
        greeting = "Привет! 👋 Я ИИ-архитектор. Я помогу вам создать собственного умного бота для вашего бизнеса за пару минут. Как называется ваша компания или продукт?"
        history = [f"Бот: {greeting}"]
        await save_session_history(session_key, history, state={"step": "collect_name"})
        return ChatResponse(reply=greeting)

    # Логика для обычных ботов
    if bot_id not in BOTS_REGISTRY:
        # Если бота нет в реестре, возможно это бот из Assistants API
        # В реальном проде тут нужно проверять базу данных
        # Пока для простоты возвращаем дефолтное приветствие
        greeting = "Здравствуйте! Чем могу помочь?"
    else:
        bot_config = BOTS_REGISTRY[bot_id]
        greeting = bot_config.get("greeting", "Здравствуйте! Чем могу помочь?")

    # Инициализируем историю с приветствием и сохраняем в Redis
    history = [f"Бот: {greeting}"]
    await save_session_history(session_key, history)

    logger.info(f"Инициализирована новая сессия для бота {bot_id}: {body.session_id}")
    return ChatResponse(reply=greeting)

@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_endpoint(request: Request, body: ChatRequest, current_user: User = Depends(get_current_user)):
    """Обработка сообщений. Берет историю из Redis."""
    bot_id = body.bot_id
    session_key = f"session:{bot_id}:{body.session_id}"

    # Получаем историю из Redis
    formatted_history = await get_session_history(session_key)
    logger.info(f"Получен запрос от сессии {session_key}: '{body.message}'. Длина истории: {len(formatted_history)}")

    # 1. Логика для Бота-Онбордера
    if bot_id == "creator_bot":
        if not onboarding_graph:
            raise HTTPException(status_code=500, detail="Бот-Онбордер не инициализирован")

        current_state = await get_onboarding_state(session_key)

        try:
            result = await onboarding_graph.execute(
                question=body.message,
                history=formatted_history,
                state_dict=current_state
            )

            response_text = result["reply"]
            new_state = result["state"]

            formatted_history.append(f"Клиент: {body.message}")
            formatted_history.append(f"Бот: {response_text}")
            await save_session_history(session_key, formatted_history, state=new_state)

            return ChatResponse(reply=response_text)

        except Exception as e:
            logger.error(f"Ошибка при обработке запроса онбординга: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

    # 2. Логика для ботов из Assistants API (если bot_id начинается с 'asst_')
    if bot_id.startswith("asst_"):
        if not assistants_adapter:
            raise HTTPException(status_code=500, detail="Assistants Adapter не инициализирован")

        state = await get_onboarding_state(session_key)
        thread_id = state.get("thread_id")

        if not thread_id:
            thread_id = await assistants_adapter.create_thread()
            state["thread_id"] = thread_id
            await save_session_history(session_key, formatted_history, state=state)

        try:
            response_text = await assistants_adapter.send_message_and_get_response(
                thread_id=thread_id,
                assistant_id=bot_id,
                message=body.message
            )

            formatted_history.append(f"Клиент: {body.message}")
            formatted_history.append(f"Бот: {response_text}")
            await save_session_history(session_key, formatted_history, state=state)

            return ChatResponse(reply=response_text)

        except Exception as e:
            logger.error(f"Ошибка при работе с Assistants API: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Ошибка при обращении к OpenAI Assistants")

    # 3. Логика для локальных ботов (LangGraph + Qdrant)
    if bot_id not in scenario_graphs:
        if bot_id in BOTS_REGISTRY and llm_adapter:
            try:
                bot_cfg = BOTS_REGISTRY[bot_id]
                system_prompt = bot_cfg.get("prompts", {}).get("support", "Ты — полезный ИИ-ассистент. Отвечай кратко и по делу.")
                system_prompt = system_prompt.replace("{context}", "Контекст недоступен, отвечай на основе общих знаний.")
                history_str = "\n".join(formatted_history[-10:])
                full_prompt = f"{system_prompt}\n\nИстория:\n{history_str}\n\nВопрос: {body.message}\n\nОтвет:"
                response_text = await llm_adapter.generate(full_prompt)
                formatted_history.append(f"Клиент: {body.message}")
                formatted_history.append(f"Бот: {response_text}")
                await save_session_history(session_key, formatted_history)
                return ChatResponse(reply=response_text)
            except Exception as e:
                logger.error(f"Fallback LLM ошибка: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Ошибка генерации ответа")
        raise HTTPException(status_code=404, detail=f"Бот с ID {bot_id} не найден")

    graph = scenario_graphs[bot_id]

    try:
        response_text = await graph.execute(
            question=body.message,
            history=formatted_history,
            session_id=body.session_id
        )

        formatted_history.append(f"Клиент: {body.message}")
        formatted_history.append(f"Бот: {response_text}")
        await save_session_history(session_key, formatted_history)

        logger.info(f"Ответ сгенерирован и сохранен в сессию {session_key}")
        return ChatResponse(reply=response_text)
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при генерации ответа")

@app.post("/api/knowledge/upload")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    bot_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Эндпоинт для загрузки PDF, Excel и текстовых файлов в базу знаний бота"""
    if not knowledge_manager:
        raise HTTPException(status_code=500, detail="Менеджер знаний не инициализирован")
        
    if bot_id not in BOTS_REGISTRY:
        # В реальном приложении здесь должна быть проверка, что bot_id принадлежит current_user в таблице UserBot
        raise HTTPException(status_code=404, detail="Бот не найден")

    # Сохраняем файл временно
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    file_location = os.path.join(temp_dir, file.filename)
    
    try:
        with open(file_location, "wb+") as file_object:
            file_object.write(await file.read())
            
        # Запускаем процесс обработки
        chunks_count = await knowledge_manager.process_and_vectorize_file(
            bot_id=bot_id, 
            file_path=file_location, 
            filename=file.filename
        )
        
        # Сохраняем информацию о загруженном файле в базу данных
        file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else 'unknown'
        new_file_record = KnowledgeFile(
            user_id=current_user.id,
            bot_id=bot_id,
            filename=file.filename,
            file_type=file_ext,
            chunks_count=chunks_count
        )
        db.add(new_file_record)
        db.commit()
        
        return {
            "status": "success", 
            "message": f"Файл {file.filename} успешно загружен и изучен ботом!",
            "chunks_added": chunks_count,
            "file_id": new_file_record.id
        }
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла {file.filename}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке файла: {str(e)}")
    finally:
        # Удаляем временный файл
        if os.path.exists(file_location):
            os.remove(file_location)

class WBSyncRequest(BaseModel):
    bot_id: str = Field(..., min_length=1, max_length=128)
    wb_api_key: str = Field(..., min_length=10)

@app.post("/api/knowledge/sync/wb")
@limiter.limit("5/minute")
async def sync_wb_products(
    request: Request,
    body: WBSyncRequest,
    current_user: User = Depends(get_current_user)
):
    """Синхронизация товаров с Wildberries по API ключу"""
    if not knowledge_manager:
        raise HTTPException(status_code=500, detail="Менеджер знаний не инициализирован")
        
    try:
        products_count = await knowledge_manager.sync_wb_products(
            bot_id=body.bot_id,
            wb_api_key=body.wb_api_key
        )
        
        return {
            "status": "success",
            "message": f"Успешно загружено {products_count} товаров с Wildberries",
            "products_added": products_count
        }
    except Exception as e:
        logger.error(f"Ошибка при синхронизации с WB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")

class OzonSyncRequest(BaseModel):
    bot_id: str = Field(..., min_length=1, max_length=128)
    ozon_client_id: str = Field(..., min_length=1)
    ozon_api_key: str = Field(..., min_length=10)

@app.post("/api/knowledge/sync/ozon")
@limiter.limit("5/minute")
async def sync_ozon_products(
    request: Request,
    body: OzonSyncRequest,
    current_user: User = Depends(get_current_user)
):
    """Синхронизация товаров с Ozon по API ключу"""
    if not knowledge_manager:
        raise HTTPException(status_code=500, detail="Менеджер знаний не инициализирован")
        
    try:
        products_count = await knowledge_manager.sync_ozon_products(
            bot_id=body.bot_id,
            ozon_client_id=body.ozon_client_id,
            ozon_api_key=body.ozon_api_key
        )
        
        return {
            "status": "success",
            "message": f"Успешно загружено {products_count} товаров с Ozon",
            "products_added": products_count
        }
    except Exception as e:
        logger.error(f"Ошибка при синхронизации с Ozon: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")

@app.get("/api/knowledge/files")
@limiter.limit("20/minute")
async def get_uploaded_files(
    request: Request,
    bot_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получить список файлов, загруженных пользователем"""
    query = db.query(KnowledgeFile).filter(KnowledgeFile.user_id == current_user.id)
    
    if bot_id:
        query = query.filter(KnowledgeFile.bot_id == bot_id)
        
    files = query.order_by(KnowledgeFile.created_at.desc()).all()
    
    return {
        "status": "success",
        "files": [
            {
                "id": f.id,
                "filename": f.filename,
                "file_type": f.file_type,
                "bot_id": f.bot_id,
                "chunks_count": f.chunks_count,
                "created_at": f.created_at.isoformat()
            } for f in files
        ]
    }


async def _ozon_api_probe(client_id: str, api_key: str, endpoint: str, payload: dict) -> dict:
    """Легкая live-проверка Ozon с возвратом HTTP-статуса и текста ошибки."""
    url = f"https://api-seller.ozon.ru{endpoint}"
    headers = {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                text = await response.text()
                data = None
                try:
                    data = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    data = None
                return {
                    "ok": response.status in (200, 201),
                    "status_code": response.status,
                    "text": text,
                    "data": data,
                }
    except asyncio.TimeoutError:
        return {"ok": False, "status_code": 408, "text": "TimeoutError", "data": None}
    except Exception as e:
        return {"ok": False, "status_code": 500, "text": str(e), "data": None}


async def _check_telegram_live_status() -> dict:
    api_id = cfg.get("TELETHON_API_ID")
    api_hash = cfg.get("TELETHON_API_HASH")
    phone = cfg.get("TELETHON_PHONE", "")

    if not api_id or not api_hash:
        return {"status": "off", "message": "Ключи не заданы"}

    client = None
    try:
        client = TelegramClient(MemorySession(), int(api_id), api_hash)
        await asyncio.wait_for(client.connect(), timeout=12)
        if client.is_connected():
            masked_phone = f"{phone[:7]}***" if phone else "скрыт"
            return {"status": "active", "message": f"Подключен, телефон: {masked_phone}"}
        return {"status": "warning", "message": "Telegram не подтвердил соединение"}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "Telethon не может подключиться, идут постоянные TimeoutError"}
    except Exception as e:
        err = str(e)
        err_lower = err.lower()
        if "timeout" in err_lower:
            return {"status": "error", "message": "Telethon не может подключиться, идут постоянные TimeoutError"}
        return {"status": "warning", "message": f"Telegram отвечает нестабильно: {err[:120]}"}
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

@app.get("/api/client/info")
@limiter.limit("30/minute")
async def get_client_info(request: Request, current_user: User = Depends(get_current_user)):
    """Возвращает информацию о клиенте: каналы, бот, тариф"""
    client_id = current_user.client_id
    if not client_id:
        return {"client_id": None, "name": current_user.display_name or current_user.email, "channels": [], "bot_id": None}

    bot_config = None
    bot_id = None
    for bid, bcfg in BOTS_REGISTRY.items():
        if bcfg.get("client_id") == client_id:
            bot_config = bcfg
            bot_id = bid
            break

    channels = []
    client_cfg_list = cfg.get("CLIENTS", [])
    client_cfg = next((c for c in client_cfg_list if c.get("id") == client_id), None)

    if client_cfg:
        if client_cfg.get("wb_api_key"):
            channels.append({"id": "wildberries", "name": "Wildberries", "status": "active",
                             "features": ["questions", "feedbacks", "chats"]})
        if client_cfg.get("ozon_client_id") and client_cfg.get("ozon_api_key"):
            channels.append({"id": "ozon", "name": "Ozon", "status": "active",
                             "features": ["questions", "reviews", "chats"]})
        if client_cfg.get("telegram_enabled"):
            channels.append({"id": "telegram", "name": "Telegram", "status": "active",
                             "features": ["qa"]})

    if bot_config and bot_config.get("channels"):
        for ch_id, ch_cfg in bot_config["channels"].items():
            if not any(c["id"] == ch_id for c in channels):
                channels.append({
                    "id": ch_id, "name": ch_cfg.get("label", ch_id),
                    "status": "setup" if ch_cfg.get("enabled") else "off",
                    "features": ch_cfg.get("features", [])
                })

    return {
        "client_id": client_id,
        "name": bot_config.get("name", client_id) if bot_config else client_id,
        "display_name": current_user.display_name or current_user.email.split("@")[0],
        "bot_id": bot_id,
        "channels": channels,
        "tariff": "pro",
    }


@app.get("/api/client/stats")
@limiter.limit("30/minute")
async def get_client_stats(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Возвращает статистику клиента из базы данных"""
    from app.adapters.db.database_adapter import DatabaseAdapter

    client_id = current_user.client_id or "next"
    db_adapter = DatabaseAdapter()

    stats = {
        "wb_questions_answered": 0,
        "wb_feedbacks_answered": 0,
        "ozon_questions_answered": 0,
        "ozon_reviews_answered": 0,
        "total_dialogs": 0,
        "channels_active": 0,
    }

    try:
        wb_q = db_adapter.count_answered("wb_questions")
        wb_f = db_adapter.count_answered("wb_feedbacks")
        oz_q = db_adapter.count_answered("ozon_questions")
        oz_r = db_adapter.count_answered("ozon_reviews")

        stats["wb_questions_answered"] = wb_q
        stats["wb_feedbacks_answered"] = wb_f
        stats["ozon_questions_answered"] = oz_q
        stats["ozon_reviews_answered"] = oz_r
        stats["total_dialogs"] = wb_q + wb_f + oz_q + oz_r
    except Exception as e:
        logger.warning(f"Не удалось получить статистику из БД: {e}")

    files_count = db.query(KnowledgeFile).filter(KnowledgeFile.user_id == current_user.id).count()
    stats["knowledge_files"] = files_count

    return stats


@app.get("/api/client/dialogs")
@limiter.limit("30/minute")
async def get_recent_dialogs(request: Request, current_user: User = Depends(get_current_user)):
    """Последние отвеченные диалоги для дашборда"""
    from app.adapters.db.database_adapter import DatabaseAdapter
    db_adapter = DatabaseAdapter()
    dialogs = db_adapter.get_recent_messages(limit=10)
    return {"dialogs": dialogs}


@app.get("/api/client/channels/check")
@limiter.limit("10/minute")
async def check_channels_live(request: Request, current_user: User = Depends(get_current_user)):
    """Проверяет реальный статус подключения к WB, Ozon и Telegram"""
    from app.adapters.channels.wildberries.client import WBClient
    from app.adapters.channels.ozon.client import OzonClient

    client_id = current_user.client_id or "next"
    client_cfg_list = cfg.get("CLIENTS", [])
    client_cfg = next((c for c in client_cfg_list if c.get("id") == client_id), None)

    results = {}

    # Wildberries
    wb_key = client_cfg.get("wb_api_key") if client_cfg else None
    if wb_key:
        try:
            wb = WBClient(api_key=wb_key)
            questions = await wb.get_unanswered_questions()
            feedbacks = await wb.get_unanswered_feedbacks()
            await wb.aclose()
            results["wildberries"] = {
                "status": "active",
                "unanswered_questions": len(questions),
                "unanswered_feedbacks": len(feedbacks),
                "message": f"{len(questions)} вопросов, {len(feedbacks)} отзывов ожидают ответа"
            }
        except Exception as e:
            err_msg = str(e)
            is_expired = "401" in err_msg or "expired" in err_msg.lower() or "unauthorized" in err_msg.lower()
            results["wildberries"] = {
                "status": "error" if is_expired else "warning",
                "unanswered_questions": 0,
                "unanswered_feedbacks": 0,
                "message": "API-ключ истёк, обновите на seller.wildberries.ru" if is_expired else f"Ошибка: {err_msg[:100]}"
            }
    else:
        results["wildberries"] = {"status": "off", "message": "Ключ не задан"}

    # Ozon
    oz_id = client_cfg.get("ozon_client_id") if client_cfg else None
    oz_key = client_cfg.get("ozon_api_key") if client_cfg else None
    if oz_id and oz_key:
        try:
            questions_probe = await _ozon_api_probe(
                oz_id,
                oz_key,
                "/v1/question/list",
                {"filter": {"status": "NEW"}, "limit": 10, "last_id": ""},
            )
            chats_probe = await _ozon_api_probe(
                oz_id,
                oz_key,
                "/v3/chat/list",
                {"filter": {"chat_status": "Opened"}, "limit": 10, "offset": 0},
            )
            reviews_probe = await _ozon_api_probe(
                oz_id,
                oz_key,
                "/v1/review/list",
                {"with_interaction_status": ["UNVIEWED", "UNANSWERED"], "limit": 10, "sort_dir": "DESC"},
            )

            questions_data = questions_probe.get("data") or {}
            chats_data = chats_probe.get("data") or {}
            reviews_data = reviews_probe.get("data") or {}

            questions_count = len(questions_data.get("questions", []) or [])
            chats_count = len(chats_data.get("chats", []) or [])
            reviews_count = len(reviews_data.get("reviews", []) or [])

            reviews_text = (reviews_probe.get("text") or "").lower()
            reviews_limited = (
                reviews_probe.get("status_code") == 403
                or "permissiondenied" in reviews_text
                or "subscription" in reviews_text
            )

            auth_broken = any(
                probe.get("status_code") in (401, 403) and not (
                    probe is reviews_probe and reviews_limited
                )
                for probe in (questions_probe, chats_probe)
            )

            if auth_broken:
                results["ozon"] = {
                    "status": "error",
                    "unanswered_questions": 0,
                    "unanswered_chats": 0,
                    "unanswered_reviews": 0,
                    "message": "Ozon API не отвечает: проверьте Client-Id и Api-Key",
                }
            elif reviews_limited:
                results["ozon"] = {
                    "status": "warning",
                    "unanswered_questions": questions_count,
                    "unanswered_chats": chats_count,
                    "unanswered_reviews": 0,
                    "message": "Отзывы не работают из-за ограничения подписки Ozon, вопросы и чаты доступны",
                }
            elif questions_probe.get("ok") or chats_probe.get("ok") or reviews_probe.get("ok"):
                results["ozon"] = {
                    "status": "active",
                    "unanswered_questions": questions_count,
                    "unanswered_chats": chats_count,
                    "unanswered_reviews": reviews_count,
                    "message": f"{questions_count} вопросов, {reviews_count} отзывов и {chats_count} чатов требуют внимания",
                }
            else:
                details = questions_probe.get("text") or chats_probe.get("text") or reviews_probe.get("text") or "неизвестная ошибка"
                results["ozon"] = {
                    "status": "warning",
                    "unanswered_questions": 0,
                    "unanswered_chats": 0,
                    "unanswered_reviews": 0,
                    "message": f"Ozon отвечает нестабильно: {details[:120]}",
                }
        except Exception as e:
            results["ozon"] = {"status": "error", "message": str(e)[:100]}
    else:
        results["ozon"] = {"status": "off", "message": "Ключи не заданы"}

    # Telegram
    results["telegram"] = await _check_telegram_live_status()

    return results


@app.get("/api/client/wb/live")
@limiter.limit("5/minute")
async def get_wb_live_data(request: Request, current_user: User = Depends(get_current_user)):
    """Получает актуальные данные с WB API для дашборда"""
    from app.adapters.channels.wildberries.client import WBClient

    client_id = current_user.client_id or "next"
    client_cfg_list = cfg.get("CLIENTS", [])
    client_cfg = next((c for c in client_cfg_list if c.get("id") == client_id), None)
    wb_key = client_cfg.get("wb_api_key") if client_cfg else None

    if not wb_key:
        raise HTTPException(status_code=400, detail="WB API-ключ не настроен")

    try:
        wb = WBClient(api_key=wb_key)
        questions = await wb.get_unanswered_questions()
        feedbacks = await wb.get_unanswered_feedbacks()
        await wb.aclose()

        return {
            "status": "ok",
            "unanswered_questions": len(questions),
            "unanswered_feedbacks": len(feedbacks),
            "questions": [
                {
                    "id": q.get("id", ""),
                    "text": q.get("text", "")[:200],
                    "product": q.get("productDetails", {}).get("productName", ""),
                    "created": q.get("createdDate", ""),
                }
                for q in (questions[:10] if isinstance(questions, list) and questions and isinstance(questions[0], dict) else [])
            ],
            "feedbacks": [
                {
                    "id": f.get("id", ""),
                    "text": f.get("text", "")[:200],
                    "product": f.get("productDetails", {}).get("productName", ""),
                    "rating": f.get("productValuation", 0),
                    "created": f.get("createdDate", ""),
                }
                for f in (feedbacks[:10] if isinstance(feedbacks, list) and feedbacks and isinstance(feedbacks[0], dict) else [])
            ],
        }
    except Exception as e:
        err = str(e)
        if "401" in err or "expired" in err.lower():
            raise HTTPException(status_code=401, detail="WB API-ключ истёк. Обновите на seller.wildberries.ru/supplier-settings/access-to-api")
        raise HTTPException(status_code=500, detail=f"Ошибка WB API: {err[:200]}")


@app.get("/health")
async def health_check():
    redis_status = "ok"
    if redis_client:
        try:
            await redis_client.ping()
        except Exception:
            redis_status = "error"
    else:
        redis_status = "not_configured"

    return {
        "status": "ok",
        "active_bots": list(scenario_graphs.keys()),
        "redis_status": redis_status
    }


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8080, reload=True)
