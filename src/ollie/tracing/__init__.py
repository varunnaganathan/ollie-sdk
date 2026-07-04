"""Optional auto-instrumentation (requires ollie-sdk[tracing])."""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from ollie.instruments import Instruments, resolve_instruments

logger = logging.getLogger("ollie.tracing")

_installed = False
_capture_content = True
_active_instruments: set[Instruments] = set()

TRACING_INSTALL_HINT = (
    "Auto-instrumentation requires optional deps. Install with: pip install 'ollie-sdk[tracing]'"
)

_LOADERS = {
    Instruments.OPENAI: ("ollie.tracing.openai_instrumentor", "instrument_openai", "uninstrument_openai"),
    Instruments.ANTHROPIC: (
        "ollie.tracing.anthropic_instrumentor",
        "instrument_anthropic",
        "uninstrument_anthropic",
    ),
    Instruments.GEMINI: ("ollie.tracing.gemini_instrumentor", "instrument_gemini", "uninstrument_gemini"),
}


def install(
    *,
    instruments: Iterable[Instruments | str] | None = None,
    block_instruments: Iterable[Instruments | str] | None = None,
    auto_instrument: bool = True,
    providers: Sequence[str] | None = None,
    capture_content: bool = True,
) -> set[Instruments]:
    """Enable OTel provider instrumentors and Ollie span adapter.

    Returns the set of instruments that were requested (after resolve).
    """
    global _installed, _capture_content, _active_instruments
    if _installed:
        return set(_active_instruments)

    wanted = resolve_instruments(
        instruments=instruments,
        block_instruments=block_instruments,
        auto_instrument=auto_instrument,
        providers=providers,
    )
    _capture_content = capture_content

    if not wanted:
        for inst, (mod_name, _, disable_name) in _LOADERS.items():
            try:
                mod = __import__(mod_name, fromlist=[disable_name])
                getattr(mod, disable_name)()
            except Exception:
                pass
        try:
            from ollie.tracing.otel_setup import shutdown_tracer_provider

            shutdown_tracer_provider()
        except Exception:
            pass
        _installed = True
        _active_instruments = set()
        logger.info("Ollie tracing: auto_instrument disabled or empty instruments set")
        return set()

    try:
        import opentelemetry  # noqa: F401
        from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
    except ImportError as exc:
        from ollie.errors import OllieError

        raise OllieError(TRACING_INSTALL_HINT) from exc

    from ollie.tracing.otel_setup import setup_tracer_provider

    # Ensure prior instrumentors are off before enabling the allowlist.
    for inst, (mod_name, _, disable_name) in _LOADERS.items():
        try:
            mod = __import__(mod_name, fromlist=[disable_name])
            getattr(mod, disable_name)()
        except Exception:
            pass

    setup_tracer_provider(capture_content=capture_content)

    enabled: set[Instruments] = set()
    for inst in sorted(wanted, key=lambda i: i.value):
        mod_name, enable_name, _ = _LOADERS[inst]
        try:
            mod = __import__(mod_name, fromlist=[enable_name])
            enable = getattr(mod, enable_name)
            if enable():
                enabled.add(inst)
        except Exception:
            logger.exception("Ollie tracing: failed to enable %s", inst.value)

    _active_instruments = enabled
    _installed = True
    return set(enabled)


def uninstall() -> None:
    global _installed, _active_instruments
    if not _installed and not _active_instruments:
        # Still try to uninstrument in case of partial state
        pass
    for inst, (mod_name, _, disable_name) in _LOADERS.items():
        try:
            mod = __import__(mod_name, fromlist=[disable_name])
            getattr(mod, disable_name)()
        except Exception:
            pass
    try:
        from ollie.tracing.otel_setup import shutdown_tracer_provider

        shutdown_tracer_provider()
    except Exception:
        pass
    _active_instruments = set()
    _installed = False


def is_installed() -> bool:
    return _installed


def active_instruments() -> set[Instruments]:
    return set(_active_instruments)
