from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExpectationEvent:
    kind: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstrumentationLog:
    events: list[ExpectationEvent] = field(default_factory=list)

    def interaction_start(self, *, index: int, source: str, target: str) -> None:
        self.events.append(
            ExpectationEvent("interaction_start", {"index": index, "source": source, "target": target})
        )

    def interaction_end(self, *, index: int) -> None:
        self.events.append(ExpectationEvent("interaction_end", {"index": index}))

    def span_start(self, *, kind: str, name: str | None = None) -> None:
        self.events.append(ExpectationEvent("span_start", {"kind": kind, "name": name}))

    def span_end(self, *, kind: str, name: str | None = None) -> None:
        self.events.append(ExpectationEvent("span_end", {"kind": kind, "name": name}))

    def feature_set(self, *, name: str, value: Any) -> None:
        self.events.append(ExpectationEvent("feature_set", {"name": name, "value": value}))


@dataclass
class RunManifest:
    seed: int | None
    case_id: str
    conversation_id: str
    tools_picked: list[str] = field(default_factory=list)
    user_language: str = "en"
    features_emitted: list[str] = field(default_factory=list)
    span_kinds: list[str] = field(default_factory=list)
    span_names: list[str] = field(default_factory=list)
    interaction_count: int = 0
    expected_span_count: int = 0
    per_ix_expected_span_count: list[int] = field(default_factory=list)
    per_ix_tools_picked: list[list[str]] = field(default_factory=list)
    log: InstrumentationLog = field(default_factory=InstrumentationLog)
    wire_payload: dict[str, Any] | None = None

    def record_feature(self, name: str) -> None:
        if name not in self.features_emitted:
            self.features_emitted.append(name)
