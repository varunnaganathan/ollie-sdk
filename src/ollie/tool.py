"""Manual tool / blind-spot instrumentation helpers."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from ollie.context import get_active_parent, get_active_workflow
from ollie.interaction_v2 import InteractionHandle
from ollie.primitives import EXTERNAL_INTERACTION

F = TypeVar("F", bound=Callable[..., Any])


class tool:
    """Context manager and decorator for custom tool interactions.

    with ollie.tool("search", input=query) as t:
        t.output = docs

    @ollie.tool("search")
    def search(query: str) -> list:
        ...
    """

    def __init__(
        self,
        name: str,
        *,
        input: str | None = None,
        parent: InteractionHandle | None = None,
    ) -> None:
        self.name = name
        self.input = input
        self.parent = parent
        self._handle: InteractionHandle | None = None

    def __enter__(self) -> InteractionHandle:
        wf = get_active_workflow()
        if wf is None:
            raise RuntimeError(
                "ollie.tool() requires an active workflow. "
                "Use: with client.workflow(name=...) as wf: ..."
            )
        parent_handle = self.parent if self.parent is not None else get_active_parent()
        self._handle = wf.interaction.start(
            name=self.name,
            primitive=EXTERNAL_INTERACTION,
            parent=parent_handle,
            input=self.input,
        )
        self._wf = wf
        return self._handle

    def __exit__(self, exc_type: type[BaseException] | None, *_: Any) -> None:
        handle = self._handle
        wf = getattr(self, "_wf", None)
        if handle is not None and wf is not None and not handle._closed:
            if exc_type is not None:
                handle.mark_success(False)
            elif handle._success is None:
                handle.mark_success(True)
            wf.interaction.end(handle, output=handle.output)
        self._handle = None

    def __call__(self, fn: F) -> F:
        tool_name = self.name or fn.__name__

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with tool(tool_name, input=self.input, parent=self.parent) as handle:
                result = fn(*args, **kwargs)
                if handle.output is None and result is not None:
                    handle.output = str(result)[:2000]
                return result

        return wrapper  # type: ignore[return-value]
