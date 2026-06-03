"""Pytest configuration for ollie-sdk (loads repo .env for live e2e)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    if (os.getenv("DATABASE_URL") or "").strip():
        return
    if os.getenv("PYTEST_SKIP_REPO_DOTENV", "").strip().lower() in ("1", "true", "yes"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    pkg = Path(__file__).resolve().parent.parent
    repo = pkg.parent.parent
    backend = repo / "ollie_sentry_backend"
    for env_path in (repo / ".env", backend / ".env"):
        if env_path.is_file():
            load_dotenv(env_path, override=env_path.name == ".env" and env_path.parent.name == "ollie_sentry_backend")


def _postgres_required() -> str | None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "postgresql" not in url.split(":", 1)[0].lower() and not url.startswith("postgresql"):
        return None
    return url


@pytest.fixture
def sdk_collector():
    import sys
    from pathlib import Path

    tests_dir = Path(__file__).resolve().parent
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from collector_server import SDKCollector

    c = SDKCollector(port=0).start()
    yield c
    c.stop()


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    url = _postgres_required()
    if not url:
        pytest.skip("Set DATABASE_URL to a PostgreSQL URL for simulated-agent live e2e")
    return url
