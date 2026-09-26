import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from openai import APIStatusError, AsyncOpenAI

from app.tools import TOOL_SCHEMAS


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


class ProviderRejection(Exception):
    pass


class LanguageModel(Protocol):
    def stream(self, messages: list[dict]) -> AsyncIterator[str | ToolCall]: ...


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

    async def stream(self, messages: list[dict]) -> AsyncIterator[str | ToolCall]:
        try:
            async for event in self._events(messages):
                yield event
        except APIStatusError as exc:
            rejection = _provider_rejection(exc)
            if rejection is None:
                raise
            raise rejection from exc

    async def _events(self, messages: list[dict]) -> AsyncIterator[str | ToolCall]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            stream=True,
        )
        try:
            pending: dict[int, dict[str, str]] = {}
            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    yield text
                for tool_delta in getattr(delta, "tool_calls", None) or []:
                    slot = pending.setdefault(
                        tool_delta.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if getattr(tool_delta, "id", None):
                        slot["id"] = tool_delta.id
                    function = getattr(tool_delta, "function", None)
                    if function is None:
                        continue
                    if getattr(function, "name", None):
                        slot["name"] = function.name
                    arguments = getattr(function, "arguments", None)
                    if arguments:
                        slot["arguments"] += arguments
            for index in sorted(pending):
                slot = pending[index]
                yield ToolCall(
                    id=slot["id"],
                    name=slot["name"],
                    arguments=_tool_arguments(slot["arguments"]),
                )
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                await asyncio.shield(close())


def _provider_rejection(exc: APIStatusError) -> ProviderRejection | None:
    if exc.status_code == 401:
        return ProviderRejection("The API key was rejected")
    if exc.status_code == 429:
        return ProviderRejection("The request was rate-limited")
    return None


def _tool_arguments(raw: str) -> dict:
    if not raw:
        return {}
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(arguments, dict):
        return {}
    return arguments
