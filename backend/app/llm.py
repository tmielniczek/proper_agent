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


@dataclass(frozen=True)
class ModelUsage:
    total_tokens: int | None
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProviderRejection(Exception):
    def __init__(self, message: str = "", *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LanguageModel(Protocol):
    def stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[str | ToolCall | ModelUsage]: ...


_FALLBACK_MODEL = "gpt-4o-mini"


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


def configured_model_name() -> str:
    load_local_env()
    return os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME") or _FALLBACK_MODEL


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

    async def stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[str | ToolCall | ModelUsage]:
        try:
            async for event in self._events(messages, tools):
                yield event
        except APIStatusError as exc:
            rejection = _provider_rejection(exc)
            if rejection is None:
                raise
            raise rejection from exc

    async def _events(
        self, messages: list[dict], tools: list[dict] | None
    ) -> AsyncIterator[str | ToolCall | ModelUsage]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=TOOL_SCHEMAS if tools is None else tools,
            stream=True,
            stream_options={"include_usage": True},
        )
        try:
            pending: dict[int, dict[str, str]] = {}
            reported_total: int | None = None
            reported_input: int | None = None
            reported_output: int | None = None
            saw_usage = False
            async for chunk in response:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    saw_usage = True
                    reported_total = getattr(usage, "total_tokens", None)
                    reported_input = getattr(usage, "prompt_tokens", None)
                    reported_output = getattr(usage, "completion_tokens", None)
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
            yield ModelUsage(
                total_tokens=reported_total if saw_usage else None,
                input_tokens=reported_input if saw_usage else None,
                output_tokens=reported_output if saw_usage else None,
            )
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                await asyncio.shield(close())


def _provider_rejection(exc: APIStatusError) -> ProviderRejection | None:
    if exc.status_code == 401:
        return ProviderRejection("The API key was rejected", status_code=401)
    if exc.status_code == 429:
        return ProviderRejection("The request was rate-limited", status_code=429)
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
