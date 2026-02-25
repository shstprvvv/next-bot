import asyncio
import random
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Sequence, Type, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_s: float = 0.5
    max_delay_s: float = 15.0
    jitter_ratio: float = 0.2


def _compute_delay_s(policy: RetryPolicy, attempt: int) -> float:
    # attempt: 1..max_attempts-1 (мы спим между попытками)
    delay = min(policy.max_delay_s, policy.base_delay_s * (2 ** (attempt - 1)))
    jitter = delay * policy.jitter_ratio
    return max(0.0, delay + random.uniform(-jitter, jitter))


async def async_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    retry_on: Sequence[Type[BaseException]],
    is_retryable: Optional[Callable[[BaseException], bool]] = None,
) -> T:
    last_exc: Optional[BaseException] = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn()
        except tuple(retry_on) as e:
            last_exc = e
            if is_retryable is not None and not is_retryable(e):
                raise
            if attempt >= policy.max_attempts:
                raise
            await asyncio.sleep(_compute_delay_s(policy, attempt))
    # unreachable, но пусть будет
    assert last_exc is not None
    raise last_exc

