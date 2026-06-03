"""Live simulated-agent e2e: backend TestClient + SDK agent (Postgres registry only)."""

from __future__ import annotations

import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
_REPO = _PKG_ROOT.parent.parent
_BACKEND = _REPO / "ollie_sentry_backend"
_SDK_SRC = _PKG_ROOT / "src"
_SDK_EXAMPLES = _PKG_ROOT / "examples"

_E2E_DIR = Path(__file__).resolve().parent
for _p in (_BACKEND, _SDK_SRC, _SDK_EXAMPLES, _E2E_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


import pytest  # noqa: E402


@pytest.fixture
def integration_session(postgres_database_url: str):
    from db import get_session_factory

    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
