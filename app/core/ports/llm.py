from typing import Protocol, Union, List, Dict, Any

class LLMClient(Protocol):
    async def generate(self, prompt: Union[str, List[Dict[str, Any]]]) -> str:
        """Генерирует ответ по готовому промпту."""
        ...
        
    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """Переводит аудио в текст."""
        ...
