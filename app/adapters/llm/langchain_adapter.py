import logging
from langchain_openai import ChatOpenAI
from app.core.ports.llm import LLMClient

logger = logging.getLogger(__name__)

class LangChainLLMAdapter(LLMClient):
    def __init__(self, api_key: str, base_url: str, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        self.client = ChatOpenAI(
            openai_api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=temperature
        )

    async def generate(self, prompt: str) -> str:
        try:
            # invoke/ainvoke в новых версиях LangChain принимает строку или список сообщений
            response = await self.client.ainvoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"[LangChainAdapter] Ошибка генерации: {e}", exc_info=True)
            # Можно вернуть дефолтный ответ или пробросить ошибку выше
            raise e
