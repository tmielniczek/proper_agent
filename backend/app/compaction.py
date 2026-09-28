from dataclasses import dataclass

from app.tokens import count_messages

CONTEXT_WINDOW = 50_000
TAIL_COUNT = 6
SUMMARY_INSTRUCTION = (
    "Write one short brief of decisions, tool results, and user asks that are still open. "
    "Drop wording the lead no longer needs."
)
SUMMARY_PREFIX = "Summary of omitted messages:\n"


@dataclass(frozen=True)
class LeadView:
    messages: list[dict]
    summary_messages: list[dict] | None
    head: tuple[dict, ...]
    tail: tuple[dict, ...]


def compaction_line(window: int) -> int:
    return window * 80 // 100


def for_model(message: dict) -> dict:
    return {key: value for key, value in message.items() if key != "_id"}


def lead_view(turns: list[dict], window: int) -> LeadView:
    public = [for_model(message) for message in turns]
    if count_messages(public) <= compaction_line(window):
        return LeadView(public, None, (), ())
    preface, stored = _preface_and_stored(turns)
    first = _first_user(stored)
    if first is None:
        return LeadView(public, None, (), ())
    head_ids = {first["_id"]}
    head: list[dict] = [first]
    if preface is not None:
        head.insert(0, preface)
    tail = tuple(
        message
        for message in _tail_including_bursts(stored)
        if message.get("_id") not in head_ids
    )
    tail_ids = {message["_id"] for message in tail}
    middle = [
        message
        for message in stored
        if message.get("_id") not in head_ids and message.get("_id") not in tail_ids
    ]
    if not middle:
        return LeadView(public, None, (), ())
    summary_messages = [
        {"role": "system", "content": SUMMARY_INSTRUCTION},
        {"role": "user", "content": _middle_text(middle)},
    ]
    return LeadView([], summary_messages, tuple(head), tail)


def with_brief(view: LeadView, brief: str) -> list[dict]:
    summary = {"role": "user", "content": SUMMARY_PREFIX + brief.strip()}
    return [for_model(message) for message in view.head] + [summary] + [
        for_model(message) for message in view.tail
    ]


def _preface_and_stored(turns: list[dict]) -> tuple[dict | None, list[dict]]:
    if turns and turns[0].get("role") == "system" and "_id" not in turns[0]:
        return turns[0], turns[1:]
    return None, list(turns)


def _tail_including_bursts(stored: list[dict]) -> list[dict]:
    if not stored:
        return []
    start = max(len(stored) - TAIL_COUNT, 0)
    while start > 0 and _tail_splits_a_burst(stored, start):
        start -= 1
    return stored[start:]


def _tail_splits_a_burst(stored: list[dict], start: int) -> bool:
    for message in stored[start:]:
        if message.get("role") != "tool":
            continue
        owner = _owner_index(stored, message.get("tool_call_id"))
        if owner is not None and owner < start:
            return True
    return False


def _owner_index(stored: list[dict], tool_call_id: object) -> int | None:
    if not isinstance(tool_call_id, str):
        return None
    for index, message in enumerate(stored):
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            if call.get("id") == tool_call_id:
                return index
    return None


def _first_user(stored: list[dict]) -> dict | None:
    for message in stored:
        if message.get("role") == "user":
            return message
    return None


def _middle_text(middle: list[dict]) -> str:
    blocks = [_as_summary_text(message) for message in middle]
    return "\n".join(block for block in blocks if block)


def _as_summary_text(message: dict) -> str:
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        parts.append(content)
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        name = function.get("name") or ""
        arguments = function.get("arguments") or ""
        rendered = f"{name} {arguments}".strip()
        if rendered:
            parts.append(rendered)
    return "\n".join(parts)
