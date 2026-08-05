"""Thin wrapper around the Ollama /api/chat endpoint with JSON-schema-checked,
retrying structured output. Every agent goes through this so LLM calls are
uniformly traced and validated before their output is trusted.
"""
import json
import time
from typing import Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from src import config

T = TypeVar("T", bound=BaseModel)


class LLMCallResult:
    def __init__(self, parsed: BaseModel, raw_text: str, latency_ms: float, attempts: int):
        self.parsed = parsed
        self.raw_text = raw_text
        self.latency_ms = latency_ms
        self.attempts = attempts


def call_structured(
    system_prompt: str,
    user_prompt: str,
    output_model: Type[T],
    *,
    model: str = config.MODEL_NAME,
    max_retries: int = config.LLM_MAX_RETRIES,
) -> LLMCallResult:
    """Call the local Ollama model and parse+validate its JSON reply into
    `output_model`. On invalid JSON/schema, retries with the validation error
    fed back to the model so it can self-correct."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    start = time.monotonic()
    for attempt in range(1, max_retries + 1):
        raw_text = _chat(messages, model)
        try:
            data = _extract_json(raw_text)
            parsed = output_model.model_validate(data)
            latency_ms = (time.monotonic() - start) * 1000
            return LLMCallResult(parsed, raw_text, latency_ms, attempt)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": raw_text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Output invalid: "
                        f"{exc}\nTrả lời lại DUY NHẤT một JSON object hợp lệ đúng schema, "
                        "không thêm giải thích, không thêm markdown."
                    ),
                }
            )

    raise RuntimeError(f"LLM failed to produce valid {output_model.__name__} after "
                        f"{max_retries} attempts: {last_error}")


def _chat(messages: list, model: str) -> str:
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": config.LLM_TEMPERATURE},
        },
        timeout=config.OLLAMA_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _extract_json(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    return json.loads(text[start : end + 1])
