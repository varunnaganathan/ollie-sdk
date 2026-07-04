from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ollie.client import Client


class SessionContext:
    """Optional grouping context; sets session_id on nested workflows."""

    def __init__(self, client: Client, session_id: str) -> None:
        self._client = client
        self.session_id = str(session_id).strip()
        self._previous: str | None = None

    def __enter__(self) -> SessionContext:
        self._previous = self._client._session_id
        self._client._session_id = self.session_id
        return self

    def __exit__(self, *args: object) -> None:
        self._client._session_id = self._previous
