import ast
import asyncio
import operator
import random

from app.memory import save_memory

SPAWN_WORKERS = "spawn_workers"
SNIPPET_LIMIT = 80

LONG_TERM_MEMORY = "long_term_memory"

DISPLAY_TEXT = {
    "get_weather": "Checking weather...",
    "search_database": "Searching database...",
    "calculator": "Calculating...",
}

_LABELS = {
    **DISPLAY_TEXT,
    LONG_TERM_MEMORY: "Saving a memory...",
}

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_database",
            "description": "Search the database for records matching a query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
]

SPAWN_SCHEMA = {
    "type": "function",
    "function": {
        "name": SPAWN_WORKERS,
        "description": (
            "Start workers on independent tasks when the user's request splits into "
            "separate pieces. For a single lookup, call get_weather, search_database, "
            "or calculator yourself. Each task must stand alone without the conversation. "
            "At most five tasks start; later tasks are refused. A blank task returns an "
            "error for that slot and does not start a worker."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered, self-contained tasks.",
                }
            },
            "required": ["tasks"],
        },
    },
}

MEMORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": LONG_TERM_MEMORY,
        "description": (
            "Call this when the user asks to remember or store something. "
            "Pass one short fact."
        ),
        "parameters": {
            "type": "object",
            "properties": {"fact": {"type": "string"}},
            "required": ["fact"],
        },
    },
}

LEAD_TOOL_SCHEMAS = [*TOOL_SCHEMAS, SPAWN_SCHEMA, MEMORY_SCHEMA]


def display_text(name: str) -> str:
    return _LABELS[name]


def task_snippet(task: str, limit: int = SNIPPET_LIMIT) -> str:
    line = " ".join(task.split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def asking_label(started: int) -> str:
    noun = "worker" if started == 1 else "workers"
    return f"Asking {started} {noun}..."


def refused_label(task: str) -> str:
    snippet = task_snippet(task)
    if snippet == "":
        return "Not started"
    return f"Not started · {snippet}"


def worker_tool_label(name: str, task: str) -> str:
    return f"{display_text(name)} · {task_snippet(task)}"


async def run_tool(name: str, arguments: dict) -> dict:
    await asyncio.sleep(random.uniform(1.0, 10.0))
    if name == LONG_TERM_MEMORY:
        return await save_memory(arguments)
    if name == "get_weather":
        return {
            "temperature": 21,
            "condition": "Sunny",
            "humidity": "45%",
            "location": arguments["location"],
        }
    if name == "search_database":
        query = arguments["query"]
        return {"results": [{"id": 101, "record": f"Mock data result for query: {query}"}]}
    if name == "calculator":
        try:
            return {"result": _basic_value(arguments["expression"])}
        except Exception:
            return {"result": 42}
    raise ValueError(f"Unknown tool: {name}")


def _basic_value(expression: str):
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST):
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    raise ValueError("unsupported expression")
