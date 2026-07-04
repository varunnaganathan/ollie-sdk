"""Control which LLM client libraries are auto-instrumented."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class Instruments(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


ALL_INSTRUMENTS: frozenset[Instruments] = frozenset(Instruments)


def _coerce_one(value: Instruments | str) -> Instruments:
    if isinstance(value, Instruments):
        return value
    key = str(value).strip().lower()
    try:
        return Instruments(key)
    except ValueError as exc:
        raise ValueError(
            f"unknown instrument {value!r}; expected one of "
            f"{sorted(i.value for i in Instruments)}"
        ) from exc


def _coerce_set(values: Iterable[Instruments | str] | None) -> set[Instruments]:
    if values is None:
        return set()
    return {_coerce_one(v) for v in values}


def resolve_instruments(
    *,
    instruments: Iterable[Instruments | str] | None = None,
    block_instruments: Iterable[Instruments | str] | None = None,
    auto_instrument: bool = True,
    providers: Iterable[str] | None = None,
) -> set[Instruments]:
    """Return the set of instruments to enable.

    - ``auto_instrument=False`` → empty set (manual workflow/tool only).
    - ``instruments`` allowlist (or ``providers`` alias); default = all known.
    - ``block_instruments`` subtracted from the allowlist.
    """
    if not auto_instrument:
        return set()

    if instruments is not None:
        allow = _coerce_set(instruments)
    elif providers is not None:
        allow = _coerce_set(providers)
    else:
        allow = set(ALL_INSTRUMENTS)

    blocked = _coerce_set(block_instruments)
    return allow - blocked
