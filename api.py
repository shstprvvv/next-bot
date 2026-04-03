import os
import logging
import time
import json
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import redis.asyncio as redis

# Импорты для авторизации и БД
from sqlalchemy.orm import Session
from app.core.database import get_db, User, UserBot
from app.core.auth import get_password_hash, verify_password, create_access_token, decode_access_token
from fastapi.security import OAuth2PasswordBearer

from app.config import load_config
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.qdrant_adapter import QdrantRetrieverAdapter
from app.core.scenarios.universal_graph import UniversalScenarioGraph
from app.core.scenarios.onboarding.graph import OnboardingScenarioGraph
from app.adapters.openai_assistants.adapter import OpenAIAssistantsAdapter
from app.core.config.bots_registry import BOTS_REGISTRY

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s")
logger = logging.getLogger("API")

load_dotenv()
cfg = load_config()

app = FastAPI(title="NextBot API", description="API для виджетов на сайтах (SaaS Architecture)")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные переменные
# Теперь мы храним графы для всех ботов
scenario_graphs: Dict[str, UniversalScenarioGraph] = {}
onboarding_graph: Optional[OnboardingScenarioGraph] = None
assistants_adapter: Optional[OpenAIAssistantsAdapter] = None

# Подключение к Redis
# По умолчанию используем localhost, если не задано в .env
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None
SESSION_TTL_SECONDS = 20 * 60  # 20 минут

@app.on_event("startup")
async def startup_event():
    global scenario_graphs, redis_client, onboarding_graph, assistants_adapter
    logger.info("Инициализация API сервера и LangGraph для всех ботов...")
    
    try:
        # Инициализация Redis
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        # Проверяем подключение
        await redis_client.ping()
        logger.info(f"Успешное подключение к Redis по адресу {REDIS_URL}")
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis: {e}")
        # В продакшене здесь можно сделать raise e, чтобы сервер не стартовал без базы
    
    try:
        # LLM у нас один на всех (можно сделать и разные, если нужно разные модели)
        llm_adapter = LangChainLLMAdapter(
            api_key=cfg.get("OPENAI_API_KEY"),
            base_url=cfg.get("OPENAI_API_BASE"),
            model_name=cfg.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        )
        
        # Инициализация адаптера для Assistants API
        assistants_adapter = OpenAIAssistantsAdapter(
            api_key=cfg.get("OPENAI_API_KEY"),
            base_url=cfg.get("OPENAI_API_BASE")
        )
        
        # Инициализация графа Онбординга
        onboarding_graph = OnboardingScenarioGraph(llm_adapter, assistants_adapter)
        
        # Инициализируем графы для каждого бота из реестра
        for bot_id, bot_config in BOTS_REGISTRY.items():
            logger.info(f"Инициализация бота: {bot_id} ({bot_config['name']})")
            
            # Для каждого бота свой ретривер (своя коллекция Qdrant)
            retriever_adapter = QdrantRetrieverAdapter(
                collection_name=bot_config["collection_name"],
                knowledge_base_path=f"{bot_id}_kb.md", # Фолбэк, если нужно пересоздать
                openai_api_key=cfg.get("OPENAI_API_KEY"),
                openai_api_base=cfg.get("OPENAI_API_BASE")
            )
            
            # Создаем универсальный граф с конфигом конкретного бота
            graph = UniversalScenarioGraph(llm_adapter, retriever_adapter, bot_config)
            scenario_graphs[bot_id] = graph
            
        logger.info(f"Успешно инициализировано ботов: {len(scenario_graphs)}")
    except Exception as e:
        logger.error(f"Ошибка при инициализации LangGraph: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Подключение к Redis закрыто.")

# Модели данных для API
class ChatRequest(BaseModel):
    bot_id: str
    message: str
    session_id: str

class ChatResponse(BaseModel):
    reply: str

class InitRequest(BaseModel):
    bot_id: str
    session_id: str

class AuthRequest(BaseModel):
    email: str
    password: str

# --- Эндпоинты Авторизации ---
@app.post("/api/auth/register")
async def register_user(request: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(request.password)
    new_user = User(email=request.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = create_access_token(data={"sub": new_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/login")
async def login_user(request: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    access_token = create_access_token(data={"sub": user.email})
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
async def init_endpoint(request: InitRequest):
    """
    Эндпоинт для инициализации чата. 
    Создает сессию и возвращает приветственное сообщение для конкретного бота.
    """
    bot_id = request.bot_id
    session_key = f"session:{bot_id}:{request.session_id}"
    
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
    
    logger.info(f"Инициализирована новая сессия для бота {bot_id}: {request.session_id}")
    return ChatResponse(reply=greeting)

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Эндпоинт для обработки сообщений.
    Берет историю из Redis.
    """
    bot_id = request.bot_id
    session_key = f"session:{bot_id}:{request.session_id}"
    
    # Получаем историю из Redis
    formatted_history = await get_session_history(session_key)
    logger.info(f"Получен запрос от сессии {session_key}: '{request.message}'. Длина истории: {len(formatted_history)}")
    
    # 1. Логика для Бота-Онбордера
    if bot_id == "creator_bot":
        if not onboarding_graph:
            raise HTTPException(status_code=500, detail="Бот-Онбордер не инициализирован")
            
        current_state = await get_onboarding_state(session_key)
        
        try:
            result = await onboarding_graph.execute(
                question=request.message,
                history=formatted_history,
                state_dict=current_state
            )
            
            response_text = result["reply"]
            new_state = result["state"]
            
            # Обновляем историю и стейт
            formatted_history.append(f"Клиент: {request.message}")
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
            
        # Для Assistants API нам нужен thread_id. Сохраним его в стейте сессии.
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
                message=request.message
            )
            
            # Обновляем локальную историю (хотя Assistants API хранит свою, нам нужна для виджета)
            formatted_history.append(f"Клиент: {request.message}")
            formatted_history.append(f"Бот: {response_text}")
            await save_session_history(session_key, formatted_history, state=state)
            
            return ChatResponse(reply=response_text)
            
        except Exception as e:
            logger.error(f"Ошибка при работе с Assistants API: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Ошибка при обращении к OpenAI Assistants")

    # 3. Логика для локальных ботов (LangGraph + Qdrant)
    if bot_id not in scenario_graphs:
        raise HTTPException(status_code=404, detail=f"Бот с ID {bot_id} не найден")
        
    graph = scenario_graphs[bot_id]
    
    try:
        # Вызываем LangGraph конкретного бота с историей из Redis
        response_text = await graph.execute(
            question=request.message,
            history=formatted_history,
            session_id=request.session_id # Передаем session_id для Langfuse
        )
        
        # Обновляем историю и сохраняем обратно в Redis
        formatted_history.append(f"Клиент: {request.message}")
        formatted_history.append(f"Бот: {response_text}")
        await save_session_history(session_key, formatted_history)
            
        logger.info(f"Ответ сгенерирован и сохранен в сессию {session_key}")
        return ChatResponse(reply=response_text)
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при генерации ответа")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8080, reload=True)
