from __future__ import annotations

SYSTEM_PROMPT = """You are a synthetic TESTING AGENT for observability pipeline QA.
You must vary your behavior across runs: choose different tools, operands, and phrasing when asked.
You help with short math and string tasks. Reply concisely with the final answer only."""


def build_user_message(*, hint: str, task: str) -> str:
    return f"{task}\n\n[testing run hint: {hint}]"
