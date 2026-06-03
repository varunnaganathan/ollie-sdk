from __future__ import annotations

import random
from typing import Any

TOOL_NAMES = [
    "math.add",
    "math.mul",
    "math.sub",
    "string.upper",
    "string.reverse",
    "string.word_count",
]


def pick_tools(rng: random.Random, *, min_tools: int, max_tools: int) -> list[str]:
    n = rng.randint(min_tools, max_tools)
    if n <= 0:
        return []
    return [rng.choice(TOOL_NAMES) for _ in range(n)]


def dispatch_tool(name: str, rng: random.Random) -> tuple[str, dict[str, Any]]:
    if name == "math.add":
        a, b = rng.randint(1, 50), rng.randint(1, 50)
        result = a + b
        return str(result), {"tool": name, "op": "add", "a": a, "b": b, "result": result}
    if name == "math.mul":
        a, b = rng.randint(2, 12), rng.randint(2, 12)
        result = a * b
        return str(result), {"tool": name, "op": "mul", "a": a, "b": b, "result": result}
    if name == "math.sub":
        a, b = rng.randint(10, 99), rng.randint(1, 9)
        result = a - b
        return str(result), {"tool": name, "op": "sub", "a": a, "b": b, "result": result}
    if name == "string.upper":
        s = rng.choice(["hello qa", "ollie sdk", "testing spans"])
        out = s.upper()
        return out, {"tool": name, "input_len": len(s), "output_len": len(out)}
    if name == "string.reverse":
        s = rng.choice(["abc", "trace", "simulate"])
        out = s[::-1]
        return out, {"tool": name, "input_len": len(s), "output_len": len(out)}
    if name == "string.word_count":
        s = "one two three four"
        wc = len(s.split())
        return str(wc), {"tool": name, "word_count": wc}
    raise ValueError(f"unknown tool: {name}")
