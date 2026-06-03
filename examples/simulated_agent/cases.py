from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimCase:
    case_id: str
    user_language: str | None  # None = random
    min_tools: int
    max_tools: int
    multi_interaction: bool
    user_task_en: str
    user_task_es: str | None = None


CASES: dict[str, SimCase] = {
    "random_single_ix": SimCase(
        case_id="random_single_ix",
        user_language=None,
        min_tools=0,
        max_tools=3,
        multi_interaction=False,
        user_task_en="You are testing observability. Pick a random math or string task and answer briefly.",
    ),
    "random_es": SimCase(
        case_id="random_es",
        user_language="es",
        min_tools=1,
        max_tools=2,
        multi_interaction=False,
        user_task_en="Answer in Spanish with a short math result.",
        user_task_es="Eres un agente de prueba. Elige una tarea matemática o de texto y responde brevemente en español.",
    ),
    "random_multi_tool": SimCase(
        case_id="random_multi_tool",
        user_language=None,
        min_tools=2,
        max_tools=3,
        multi_interaction=False,
        user_task_en="Run at least two different tool-style operations conceptually and summarize.",
    ),
    "random_multi_ix": SimCase(
        case_id="random_multi_ix",
        user_language=None,
        min_tools=1,
        max_tools=2,
        multi_interaction=True,
        user_task_en="First plan a tool task, then describe execution.",
    ),
}


def get_case(case_id: str) -> SimCase:
    if case_id not in CASES:
        raise KeyError(f"unknown case_id: {case_id}; choose from {sorted(CASES)}")
    return CASES[case_id]
