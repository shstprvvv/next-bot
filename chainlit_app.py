import os
import chainlit as cl
from app.config import load_config
from app.adapters.llm.langchain_adapter import LangChainLLMAdapter
from app.adapters.retriever.qdrant_adapter import QdrantRetrieverAdapter
from app.core.use_cases.answer_question import AnswerQuestionUseCase

# Загружаем конфиг
cfg = load_config()

@cl.on_chat_start
async def start():
    # Инициализируем адаптеры (только то, что нужно для чата)
    # Используем try-except для отладки инициализации
    try:
        llm_adapter = LangChainLLMAdapter(
            api_key=cfg.get("OPENAI_API_KEY"),
            base_url=cfg.get("OPENAI_API_BASE"),
            model_name=cfg.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        )
        
        retriever_adapter = QdrantRetrieverAdapter(
            collection_name="sales_bot_knowledge",
            knowledge_base_path="sales_knowledge_base.md",
            openai_api_key=cfg.get("OPENAI_API_KEY"),
            openai_api_base=cfg.get("OPENAI_API_BASE")
        )
        
        # Создаем Use Case
        answer_use_case = AnswerQuestionUseCase(llm_adapter, retriever_adapter)
        
        # Сохраняем в сессию пользователя
        cl.user_session.set("answer_use_case", answer_use_case)
        cl.user_session.set("chat_history", [])
        
        await cl.Message(content="Привет! 👋 Я — ИИ-ассистент, созданный на платформе Next AI. Я могу заменить 80% вашей службы поддержки на маркетплейсах. Расскажите, что вы продаете, и я покажу, как смогу вам помочь!").send()
    except Exception as e:
        import logging
        logging.error(f"Ошибка при старте чата: {e}", exc_info=True)
        await cl.Message(content=f"Произошла ошибка при инициализации: {e}").send()

@cl.on_message
async def main(message: cl.Message):
    # Получаем Use Case из сессии
    answer_use_case = cl.user_session.get("answer_use_case")
    history = cl.user_session.get("chat_history", [])
    
    # Создаем пустой ответ для стриминга (если нужно) или просто отправляем результат
    msg = cl.Message(content="")
    
    # Вызываем логику ответа
    # В текущей реализации answer_question возвращает строку, 
    # но мы можем позже добавить стриминг
    response = await answer_use_case.execute(
        user_id="chainlit_user", 
        question=message.content, 
        history=history,
        source="sales_chat"
    )
    
    # Обновляем историю
    history.append(f"Клиент: {message.content}")
    history.append(f"Бот: {response}")
    cl.user_session.set("chat_history", history[-10:]) # Храним последние 10 сообщений
    
    msg.content = response
    await msg.send()
