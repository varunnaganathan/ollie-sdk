from __future__ import annotations

import os

from simulated_agent.prompts import SYSTEM_PROMPT, build_user_message


def complete(*, user_message: str, model: str | None = None) -> tuple[str, str]:
    """Returns (response_text, model_name)."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for simulated agent")

    model_name = (model or os.getenv("OLLIE_SIM_OPENAI_MODEL") or "gpt-4o-mini").strip()

    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("install openai: pip install openai") from e

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=120,
        temperature=0.7,
    )
    text = (resp.choices[0].message.content or "").strip()
    return text, model_name


def confidence_band(response_len: int) -> str:
    if response_len > 80:
        return "high"
    if response_len > 30:
        return "medium"
    return "low"
