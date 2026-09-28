import os

import tiktoken

_stable_token_ids: dict[str, int] = {}


def count_messages(messages: list[dict]) -> int:
    encoding = _encoding()
    total = 0
    for message in messages:
        text = _countable_text(message)
        if text:
            total += len(encoding.encode(text))
    return total


def text_with_tokens(count: int) -> str:
    if count == 0:
        return ""
    encoding = _encoding()
    token_id = _stable_token_id(encoding)
    return encoding.decode([token_id] * count)


def _encoding():
    model = os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME")
    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            pass
    return tiktoken.get_encoding("o200k_base")


def _stable_token_id(encoding) -> int:
    cached = _stable_token_ids.get(encoding.name)
    if cached is not None:
        return cached
    preferred = encoding.encode("\x01")
    if len(preferred) == 1 and _repeats(encoding, preferred[0]):
        _stable_token_ids[encoding.name] = preferred[0]
        return preferred[0]
    for token_id in range(encoding.n_vocab):
        if _repeats(encoding, token_id):
            _stable_token_ids[encoding.name] = token_id
            return token_id
    raise RuntimeError("tokenizer has no stable token")


def _repeats(encoding, token_id: int) -> bool:
    repeated = encoding.decode([token_id, token_id, token_id, token_id])
    return encoding.encode(repeated) == [token_id, token_id, token_id, token_id]


def _countable_text(message: dict) -> str:
    pieces: list[str] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        pieces.append(content)
    tool_call_id = message.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id:
        pieces.append(tool_call_id)
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        name = function.get("name") or ""
        arguments = function.get("arguments") or ""
        pieces.append(f"{name} {arguments}".strip())
    return "\n".join(pieces)
