"""Active workflow / interaction context for auto-instrumentation attach."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ollie.interaction_v2 import InteractionHandle
    from ollie.workflow import WorkflowSession

_active_workflow: ContextVar[WorkflowSession | None] = ContextVar("ollie_active_workflow", default=None)
_active_interaction: ContextVar[InteractionHandle | None] = ContextVar(
    "ollie_active_interaction", default=None
)


def get_active_workflow() -> WorkflowSession | None:
    return _active_workflow.get()


def get_active_interaction() -> InteractionHandle | None:
    return _active_interaction.get()


def get_active_parent() -> InteractionHandle | None:
    """Parent for auto-recorded interactions: current open interaction, else workflow root."""
    current = _active_interaction.get()
    if current is not None and not current._closed:
        return current
    wf = _active_workflow.get()
    if wf is not None and wf._root is not None and not wf._root._closed:
        return wf._root
    return None


def set_active_workflow(workflow: WorkflowSession | None) -> Token:
    return _active_workflow.set(workflow)


def reset_active_workflow(token: Token) -> None:
    _active_workflow.reset(token)


def set_active_interaction(handle: InteractionHandle | None) -> Token:
    return _active_interaction.set(handle)


def reset_active_interaction(token: Token) -> None:
    _active_interaction.reset(token)
