from __future__ import annotations
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
)


@dataclass
class SafeResult:
    ok: bool
    request_id: str
    content: Optional[str] = None
    error_user: Optional[str] = None
    error_debug: Optional[str] = None
    latency_ms: Optional[int] = None
    retry_count: int = 0


def _is_transient(e: Exception) -> bool:
    msg = str(e).lower()
    return any(
        k in msg
        for k in [
            "timeout",
            "timed out",
            "rate limit",
            "429",
            "overloaded",
            "503",
            "502",
            "connection",
        ]
    )


def safe_invoke(logger, *, user_error: str, fn: Callable[[], Any]) -> SafeResult:
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    retries = {"count": 0}

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=3.0),
        retry=retry_if_exception(lambda e: _is_transient(e)),
    )
    def _run():
        try:
            return fn()
        except Exception as e:
            retries["count"] += 1
            logger.warning(
                f"request_id={request_id} transient_error retry={retries['count']} err={type(e).__name__}:{e}"
            )
            raise

    try:
        resp = _run()
        latency = int((time.time() - start) * 1000)
        content = getattr(resp, "content", None)
        if content is None:
            content = str(resp)
        return SafeResult(
            ok=True,
            request_id=request_id,
            content=content,
            latency_ms=latency,
            retry_count=max(0, retries["count"] - 1),
        )
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        logger.error(
            f"request_id={request_id} model_call_failed latency_ms={latency} err={type(e).__name__}:{e}"
        )
        return SafeResult(
            ok=False,
            request_id=request_id,
            error_user=user_error,
            error_debug=f"{type(e).__name__}: {e}",
            latency_ms=latency,
            retry_count=max(0, retries["count"] - 1),
        )
