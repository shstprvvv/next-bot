import logging
import os
from typing import Union, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from app.core.ports.llm import LLMClient
from app.utils.retry import RetryPolicy, async_retry

logger = logging.getLogger(__name__)

class LangChainLLMAdapter(LLMClient):
    def __init__(self, api_key: str, base_url: str, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        timeout_s = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))

        self.client = ChatOpenAI(
            openai_api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=temperature,
            timeout=timeout_s,
            # Ретраи делаем централизованно ниже, чтобы не было "двойных" повторов.
            max_retries=0,
        )
        self._retry_policy = RetryPolicy(
            max_attempts=max(1, max_retries + 1),
            base_delay_s=float(os.getenv("LLM_RETRY_BASE_DELAY_SECONDS", "0.75")),
            max_delay_s=float(os.getenv("LLM_RETRY_MAX_DELAY_SECONDS", "12")),
        )

        self._retry_on = self._build_retryable_exceptions()

    async def generate(self, prompt: Union[str, List[Dict[str, Any]]]) -> str:
        async def _call():
            # Если пришел список (например, с картинкой), оборачиваем в HumanMessage
            if isinstance(prompt, list):
                messages = [HumanMessage(content=prompt)]
                return await self.client.ainvoke(messages)
            # Иначе просто отправляем строку
            return await self.client.ainvoke(prompt)

        try:
            response = await async_retry(
                _call,
                policy=self._retry_policy,
                retry_on=self._retry_on,
                is_retryable=self._is_retryable_error,
            )
            return response.content
        except Exception as e:
            logger.error(f"[LangChainAdapter] Ошибка генерации: {e}", exc_info=True)
            raise

    @staticmethod
    def _build_retryable_exceptions():
        retry_on = []
        try:
            import httpx  # type: ignore

            retry_on.extend([httpx.TimeoutException, httpx.TransportError, httpx.HTTPError])
        except Exception:
            pass

        # openai-python (через langchain_openai) может выбрасывать эти исключения
        try:
            import openai  # type: ignore

            candidates = []
            for name in [
                "RateLimitError",
                "APITimeoutError",
                "APIConnectionError",
                "InternalServerError",
                "APIStatusError",
            ]:
                exc = getattr(openai, name, None)
                if exc is not None:
                    candidates.append(exc)
            retry_on.extend(candidates)
        except Exception:
            pass

        # Фоллбек: если ничего не нашли, ретраить будем хотя бы на Exception не нужно.
        return tuple(set(retry_on)) if retry_on else (Exception,)

    @staticmethod
    def _is_retryable_error(e: BaseException) -> bool:
        # Не ретраим явные ошибки конфигурации/валидации и т.п.
        msg = str(e).lower()
        if "invalid api key" in msg or "api key" in msg and "invalid" in msg:
            return False
        if "authentication" in msg:
            return False

        # Не ретраим большинство 4xx (кроме 429)
        status = getattr(e, "status_code", None)
        if status is None:
            # openai.APIStatusError часто хранит response
            resp = getattr(e, "response", None)
            status = getattr(resp, "status_code", None)
        if status is not None:
            try:
                status_i = int(status)
                if 400 <= status_i <= 499 and status_i != 429:
                    return False
            except Exception:
                pass
        return True
