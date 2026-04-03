import os
import logging
import chainlit as cl
from app.config import load_config
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.qdrant_adapter import QdrantRetrieverAdapter

# Импортируем наш новый граф
from app.core.scenarios.messenger_graph import MessengerScenarioGraph

# Настраиваем логирование для Chainlit
logger = logging.getLogger("ChainlitApp")
logger.setLevel(logging.INFO)

# Загружаем конфиг
cfg = load_config()

@cl.on_chat_start
async def start():
    logger.info("[Chainlit] Новая сессия начата. Инициализация...")
    try:
        # Инициализируем адаптеры
        llm_adapter = LangChainLLMAdapter(
            api_key=cfg.get("OPENAI_API_KEY"),
            base_url=cfg.get("OPENAI_API_BASE"),
            model_name=cfg.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        )
        logger.info("[Chainlit] LLM Adapter инициализирован.")
        
        # Подключаем новую базу знаний мессенджера
        retriever_adapter = QdrantRetrieverAdapter(
            collection_name="messenger_knowledge",
            knowledge_base_path="messenger_kb.md",
            openai_api_key=cfg.get("OPENAI_API_KEY"),
            openai_api_base=cfg.get("OPENAI_API_BASE")
        )
        logger.info("[Chainlit] Retriever Adapter инициализирован.")
        
        # Создаем Граф-сценарий вместо старого UseCase
        scenario_graph = MessengerScenarioGraph(llm_adapter, retriever_adapter)
        
        # Сохраняем в сессию пользователя
        cl.user_session.set("scenario_graph", scenario_graph)
        cl.user_session.set("chat_history", [])
        logger.info("[Chainlit] Граф сохранен в сессию.")
        
        msg = cl.Message(content="Привет! 👋 Я — ИИ-ассистент мессенджера «Связь». Я могу рассказать о преимуществах нашего защищенного корпоративного мессенджера или помочь с техническими вопросами. Что вас интересует?")
        await msg.send()
    except Exception as e:
        logger.error(f"[Chainlit] Ошибка при старте чата: {e}", exc_info=True)
        msg = cl.Message(content=f"Произошла ошибка при инициализации: {e}")
        await msg.send()

@cl.on_message
async def main(message: cl.Message):
    logger.info(f"[Chainlit] Получено сообщение: '{message.content}'")
    
    # Получаем Граф из сессии
    scenario_graph = cl.user_session.get("scenario_graph")
    history = cl.user_session.get("chat_history", [])
    
    if not scenario_graph:
        logger.warning("[Chainlit] Сессия устарела (scenario_graph не найден).")
        msg = cl.Message(content="Сессия устарела. Пожалуйста, обновите страницу (F5) или нажмите 'New Chat'.")
        await msg.send()
        return
        
    msg = cl.Message(content="")
    await msg.send()
    
    # Вызываем логику графа
    try:
        logger.info("[Chainlit] Передаю запрос в граф...")
        response = await scenario_graph.execute(
            question=message.content, 
            history=history
        )
        logger.info(f"[Chainlit] Получен ответ от графа: '{response[:50]}...'")
        
        # Обновляем историю
        history.append(f"Клиент: {message.content}")
        history.append(f"Бот: {response}")
        cl.user_session.set("chat_history", history[-10:])
        
        msg.content = response
        await msg.update()
    except Exception as e:
        logger.error(f"[Chainlit] Ошибка при генерации ответа: {e}", exc_info=True)
        msg.content = "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
        await msg.update()
