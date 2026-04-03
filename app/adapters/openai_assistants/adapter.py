import logging
import asyncio
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI

logger = logging.getLogger("OpenAIAssistantsAdapter")
logger.setLevel(logging.INFO)

class OpenAIAssistantsAdapter:
    """
    Адаптер для работы с OpenAI Assistants API (v2).
    Позволяет создавать ботов, загружать им файлы (базы знаний) и вести диалоги (Threads).
    """
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        # Если base_url передан (например, для proxyapi.ru), используем его
        kwargs = {
            "api_key": api_key,
            "default_headers": {"OpenAI-Beta": "assistants=v2"}
        }
        if base_url:
            kwargs["base_url"] = base_url
            
        self.client = AsyncOpenAI(**kwargs)
        logger.info("[Init] OpenAIAssistantsAdapter инициализирован.")

    async def create_assistant(self, name: str, instructions: str, model: str = "gpt-4o-mini", file_ids: List[str] = None) -> str:
        """
        Создает нового ассистента в OpenAI.
        Возвращает assistant_id.
        """
        logger.info(f"Создание нового ассистента '{name}'...")
        
        tools = []
        tool_resources = None
        
        # Если есть файлы, включаем инструмент file_search (RAG из коробки)
        if file_ids:
            tools.append({"type": "file_search"})
            
            # В новых версиях библиотеки vector_stores находится прямо в client
            # Создаем векторное хранилище для этого ассистента
            vector_store = await self.client.vector_stores.create(name=f"{name}_Knowledge")
            
            # Добавляем файлы в векторное хранилище
            await self.client.vector_stores.file_batches.create(
                vector_store_id=vector_store.id,
                file_ids=file_ids
            )
            
            tool_resources = {
                "file_search": {
                    "vector_store_ids": [vector_store.id]
                }
            }

        assistant = await self.client.beta.assistants.create(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            tool_resources=tool_resources
        )
        
        logger.info(f"Ассистент '{name}' успешно создан. ID: {assistant.id}")
        return assistant.id

    async def upload_file_from_text(self, text_content: str, filename: str = "knowledge.txt") -> str:
        """
        Загружает текстовый контент как файл в OpenAI для использования в RAG.
        Возвращает file_id.
        """
        import tempfile
        import os
        
        logger.info(f"Загрузка файла знаний '{filename}' в OpenAI...")
        
        # Создаем временный файл, так как OpenAI API требует физический файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_file.write(text_content)
            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, "rb") as f:
                file_obj = await self.client.files.create(
                    file=f,
                    purpose="assistants",
                    extra_headers={"OpenAI-Beta": "assistants=v2"}
                )
            logger.info(f"Файл успешно загружен. ID: {file_obj.id}")
            return file_obj.id
        finally:
            os.remove(temp_file_path)

    async def create_thread(self) -> str:
        """Создает новый диалог (Thread). Возвращает thread_id."""
        thread = await self.client.beta.threads.create()
        return thread.id

    async def send_message_and_get_response(self, thread_id: str, assistant_id: str, message: str) -> str:
        """
        Отправляет сообщение в тред, запускает ассистента и ждет ответ.
        """
        # 1. Добавляем сообщение пользователя в тред
        await self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )
        
        # 2. Запускаем ассистента
        run = await self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id
        )
        
        # 3. Ждем завершения (поллинг)
        # В реальном проде лучше использовать Streaming, но для простоты пока поллинг
        while run.status in ['queued', 'in_progress', 'cancelling']:
            await asyncio.sleep(1)
            run = await self.client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            
        if run.status == 'completed':
            # 4. Получаем ответ
            messages = await self.client.beta.threads.messages.list(
                thread_id=thread_id
            )
            # Первое сообщение в списке - это последний ответ ассистента
            latest_message = messages.data[0]
            return latest_message.content[0].text.value
        else:
            logger.error(f"Ошибка выполнения Run: {run.status}, {run.last_error}")
            return "Извините, произошла ошибка при генерации ответа."
