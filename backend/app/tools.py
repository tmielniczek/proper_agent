import ast
import asyncio
import operator
import random

DISPLAY_TEXT = {
    "get_weather": "Checking weather...",
    "search_database": "Searching database...",
    "calculator": "Calculating...",
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


def display_text(name: str) -> str:
    return DISPLAY_TEXT[name]


async def run_tool(name: str, arguments: dict) -> dict:
    await asyncio.sleep(random.uniform(1.0, 10.0))
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
