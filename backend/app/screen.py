import re
from dataclasses import dataclass

_SSN = re.compile(r"\d{3}-\d{2}-\d{4}")
_CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_SECRET = re.compile(r"(password|api_key):", re.IGNORECASE)

PHRASE_LIST = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore your instructions",
    "ignore the instructions",
    "disregard your instructions",
    "disregard the instructions",
    "reveal your system prompt",
    "show your system prompt",
    "print your system prompt",
    "what is your system prompt",
)

PHRASE_LIST_REFUSAL = (
    "Stopped: that request asks to ignore instructions or reveal the system prompt."
)


@dataclass(frozen=True)
class MaskResult:
    text: str
    note: str | None


def matches_phrase_list(text: str) -> bool:
    lowered = text.casefold()
    return any(phrase in lowered for phrase in PHRASE_LIST)


def mask_prompt(text: str) -> MaskResult:
    ssn_count = 0
    card_count = 0
    secret_count = 0
    lines: list[str] = []
    for line in text.split("\n"):
        masked, ssns, cards, secrets = _mask_line(line)
        lines.append(masked)
        ssn_count += ssns
        card_count += cards
        secret_count += secrets
    note = _note(ssn_count, card_count, secret_count)
    return MaskResult(text="\n".join(lines), note=note)


def _mask_line(line: str) -> tuple[str, int, int, int]:
    match = _SECRET.search(line)
    if match is None:
        masked, ssns, cards = _mask_numbers(line)
        return masked, ssns, cards, 0
    prefix, ssns, cards = _mask_numbers(line[: match.start()])
    label = match.group(0)
    return f"{prefix}{label}[secret]", ssns, cards, 1


def _mask_numbers(text: str) -> tuple[str, int, int]:
    ssn_count = 0
    parts: list[str] = []
    last = 0
    for match in _SSN.finditer(text):
        parts.append(text[last : match.start()])
        parts.append("[ssn]")
        ssn_count += 1
        last = match.end()
    parts.append(text[last:])
    after_ssn = "".join(parts)

    card_count = 0
    parts = []
    last = 0
    for match in _CARD.finditer(after_ssn):
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            parts.append(after_ssn[last : match.start()])
            parts.append("[card number]")
            card_count += 1
            last = match.end()
    parts.append(after_ssn[last:])
    return "".join(parts), ssn_count, card_count


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _note(ssn_count: int, card_count: int, secret_count: int) -> str | None:
    parts: list[str] = []
    if ssn_count:
        label = "social security number" if ssn_count == 1 else "social security numbers"
        parts.append(f"{ssn_count} {label}")
    if card_count:
        label = "card number" if card_count == 1 else "card numbers"
        parts.append(f"{card_count} {label}")
    if secret_count:
        label = "secret" if secret_count == 1 else "secrets"
        parts.append(f"{secret_count} {label}")
    if not parts:
        return None
    return "Screen: masked " + ", ".join(parts)
