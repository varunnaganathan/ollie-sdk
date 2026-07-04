from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

from ollie.primitives import BUILTIN_PRIMITIVES
from ollie.trace import utc_now_iso

if TYPE_CHECKING:
    from ollie.workflow import WorkflowSession


class InteractionHandle:
    """Open interaction handle returned by WorkflowInteractionController.start()."""

    def __init__(
        self,
        workflow: WorkflowSession,
        *,
        interaction_ref: str,
        parent_interaction_ref: str | None,
        name: str,
        primitive: str | None,
        input: str | None,
        started_at: str,
    ) -> None:
        self._workflow = workflow
        self.interaction_ref = interaction_ref
        self.parent_interaction_ref = parent_interaction_ref
        self.name = name
        self.primitive = primitive
        self._input = input
        self._output: str | None = None
        self._started_at = started_at
        self._ended_at: str | None = None
        self._attributes: list[dict[str, Any]] = []
        self._closed = False
        self._success: bool | None = None

    @property
    def input(self) -> str | None:
        return self._input

    @input.setter
    def input(self, value: str | None) -> None:
        self._input = value

    @property
    def output(self) -> str | None:
        return self._output

    @output.setter
    def output(self, value: str | None) -> None:
        self._output = value

    def mark_success(self, success: bool = True) -> None:
        self._success = bool(success)
        self._set_attr("success", bool(success))
        self._set_attr("status", "ok" if success else "error")

    def _set_attr(self, name: str, value: bool | int | float | str) -> None:
        self._attributes = [a for a in self._attributes if a.get("name") != name]
        self._attributes.append({"name": name, "value": value})

    def attribute(self, name: str, value: bool | int | float | str) -> None:
        self._set_attr(name, value)
        if name == "success":
            self._success = bool(value)

    def _close(self, *, output: str | None = None) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError(f"interaction {self.interaction_ref!r} already ended")
        if output is not None:
            self._output = output
        self._ended_at = utc_now_iso()
        if self._success is None and self.primitive is not None:
            self.mark_success(True)
        self._closed = True
        return self._to_wire_dict()

    def _to_wire_dict(self) -> dict[str, Any]:
        return {
            "interaction_ref": self.interaction_ref,
            "parent_interaction_ref": self.parent_interaction_ref,
            "name": self.name,
            "primitive": self.primitive,
            "input": self._input,
            "output": self._output,
            "events": {"trigger": [], "context": [], "spans": []},
            "attributes": list(self._attributes),
            "started_at": self._started_at,
            "ended_at": self._ended_at or utc_now_iso(),
        }


class WorkflowInteractionController:
    def __init__(self, workflow: WorkflowSession) -> None:
        self._workflow = workflow

    def start(
        self,
        name: str,
        *,
        primitive: str | None = None,
        parent: InteractionHandle | None = None,
        input: str | None = None,
    ) -> InteractionHandle:
        if primitive is not None and primitive not in BUILTIN_PRIMITIVES:
            raise ValueError(f"unknown primitive {primitive!r}; expected one of {sorted(BUILTIN_PRIMITIVES)}")
        return self._workflow._start_interaction(
            name=name,
            primitive=primitive,
            parent=parent,
            input=input,
        )

    def end(self, handle: InteractionHandle, *, output: str | None = None) -> None:
        self._workflow._end_interaction(handle, output=output)

    @contextmanager
    def open(
        self,
        name: str,
        *,
        primitive: str | None = None,
        parent: InteractionHandle | None = None,
        input: str | None = None,
    ) -> Iterator[InteractionHandle]:
        handle = self.start(name, primitive=primitive, parent=parent, input=input)
        try:
            yield handle
        except Exception:
            handle.mark_success(False)
            raise
        finally:
            if not handle._closed:
                self.end(handle, output=handle.output)

    def __call__(
        self,
        name: str,
        *,
        primitive: str | None = None,
        parent: InteractionHandle | None = None,
        input: str | None = None,
    ) -> Iterator[InteractionHandle]:
        return self.open(name, primitive=primitive, parent=parent, input=input)
