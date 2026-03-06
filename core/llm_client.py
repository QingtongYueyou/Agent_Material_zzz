from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config.settings import LLM_MODEL_ID, LLM_TIMEOUT_SEC, POE_API_BASE_URL, POE_API_KEY


class LLMClientError(RuntimeError):
    pass


def _chat_completions_url() -> str:
    base = POE_API_BASE_URL.rstrip("/")
    return f"{base}/chat/completions"


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 900,
    timeout_sec: int | None = None,
) -> str:
    if not POE_API_KEY:
        raise LLMClientError("POE_API_KEY ???")

    payload: dict[str, Any] = {
        "model": model or LLM_MODEL_ID,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    req = urllib.request.Request(
        _chat_completions_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {POE_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec or LLM_TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = str(e)
        raise LLMClientError(f"LLM HTTP ??: {detail}") from e
    except Exception as e:
        raise LLMClientError(f"LLM ????: {e}") from e

    try:
        data = json.loads(body)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise LLMClientError(f"LLM ??????: {e}") from e
