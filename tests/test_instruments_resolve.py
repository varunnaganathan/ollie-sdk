from __future__ import annotations

import pytest

from ollie.instruments import Instruments, resolve_instruments


def test_default_all_instruments():
    assert resolve_instruments() == {Instruments.OPENAI, Instruments.ANTHROPIC, Instruments.GEMINI}


def test_auto_instrument_false_empty():
    assert resolve_instruments(auto_instrument=False) == set()
    assert resolve_instruments(auto_instrument=False, instruments={Instruments.OPENAI}) == set()


def test_allowlist_enum_and_string():
    assert resolve_instruments(instruments={Instruments.ANTHROPIC}) == {Instruments.ANTHROPIC}
    assert resolve_instruments(instruments=["openai", "gemini"]) == {
        Instruments.OPENAI,
        Instruments.GEMINI,
    }


def test_block_instruments():
    assert resolve_instruments(block_instruments={Instruments.OPENAI}) == {
        Instruments.ANTHROPIC,
        Instruments.GEMINI,
    }
    assert resolve_instruments(
        instruments={Instruments.OPENAI, Instruments.ANTHROPIC},
        block_instruments=["openai"],
    ) == {Instruments.ANTHROPIC}


def test_providers_alias():
    assert resolve_instruments(providers=["openai"]) == {Instruments.OPENAI}


def test_instruments_wins_over_providers():
    assert resolve_instruments(
        instruments={Instruments.GEMINI},
        providers=["openai"],
    ) == {Instruments.GEMINI}


def test_unknown_instrument_raises():
    with pytest.raises(ValueError, match="unknown instrument"):
        resolve_instruments(instruments=["nope"])
