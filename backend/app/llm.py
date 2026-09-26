import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from openai import AsyncOpenAI


class LanguageModel(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def model_from_env() -> "OpenAILanguageModel":
    load_local_env()
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME")
    if not api_key or not model:
        raise RuntimeError("Set OPENAI_API_KEY and MODEL_NAME, or LLM_API_KEY and LLM_MODEL")
    return OpenAILanguageModel(api_key=api_key, model=model)


class OpenAILanguageModel:
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
        )
        async for chunk in response:
            if not chunk.choices:
                continue
            text = chunk.choices[0].delta.content
            if text:
                yield text
