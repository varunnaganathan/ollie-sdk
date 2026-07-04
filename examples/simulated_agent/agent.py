from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ollie.primitives import DELEGATION, EXTERNAL_INTERACTION, GENERATION
from simulated_agent.cases import SimCase
from simulated_agent.expectations import RunManifest
from simulated_agent.llm import complete, confidence_band
from simulated_agent.prompts import build_user_message
from simulated_agent.tools import dispatch_tool, pick_tools

if TYPE_CHECKING:
    from ollie.client import Client


def _run_workflow_body(
    wf,
    *,
    case: SimCase,
    manifest: RunManifest,
    rng: random.Random,
    user_text: str,
    lang: str,
) -> str:
    manifest.log.interaction_start(index=0, source="workflow", target="agent")
    started = time.perf_counter()
    final_output = ""
    tool_results: list[str] = []

    with wf.interaction(name="Plan Response", primitive=GENERATION, parent=wf._root) as plan_ix:
        manifest.log.span_start(kind="generation", name="Plan Response")
        plan_ix.input = user_text
        plan_ix.event("llm_started")
        llm_text, model_name = complete(user_message=user_text)
        plan_ix.event("llm_completed", payload={"model": model_name, "response_len": len(llm_text)})
        manifest.record_feature("llm_response_char_count")
        plan_ix.attribute("llm_response_char_count", len(llm_text))
        manifest.log.feature_set(name="llm_response_char_count", value=len(llm_text))

        band = confidence_band(len(llm_text))
        manifest.record_feature("agent_confidence_band")
        plan_ix.attribute("agent_confidence_band", band)
        manifest.log.feature_set(name="agent_confidence_band", value=band)
        plan_ix.attribute("model_family", model_name.split("-")[0] if model_name else "openai")
        manifest.log.span_end(kind="generation", name="Plan Response")
        manifest.span_kinds.append("generation")

        tools = pick_tools(rng, min_tools=case.min_tools, max_tools=case.max_tools)
        manifest.tools_picked = list(tools)
        manifest.per_ix_tools_picked.append(list(tools))

        with wf.interaction(name="Dispatch Tools", primitive=DELEGATION, parent=plan_ix) as dispatch_ix:
            manifest.log.span_start(kind="delegation", name="Dispatch Tools")
            manifest.span_kinds.append("delegation")
            dispatch_ix.attribute("tool_count", len(tools))

            for tool_name in tools:
                with wf.interaction(
                    name=tool_name,
                    primitive=EXTERNAL_INTERACTION,
                    parent=dispatch_ix,
                ) as tool_ix:
                    manifest.log.span_start(kind="external_interaction", name=tool_name)
                    manifest.span_kinds.append("external_interaction")
                    manifest.span_names.append(tool_name)
                    tool_ix.event("tool_invoked", payload={"tool": tool_name})
                    result, payload = dispatch_tool(tool_name, rng)
                    tool_ix.event("tool_completed", payload=dict(payload))
                    tool_ix.output = result[:200]
                    tool_results.append(result)
                    manifest.record_feature("last_tool_result_size")
                    tool_ix.attribute("last_tool_result_size", len(result))
                    manifest.log.feature_set(name="last_tool_result_size", value=len(result))
                    manifest.log.span_end(kind="external_interaction", name=tool_name)

            manifest.log.span_end(kind="delegation", name="Dispatch Tools")

        plan_ix.output = llm_text
        final_output = llm_text
        if tool_results:
            final_output = f"{llm_text} | tools: {', '.join(tool_results)}"

    manifest.record_feature("user_language")
    manifest.record_feature("response_char_count")
    manifest.record_feature("tools_invoked_count")
    manifest.record_feature("retry_count")
    manifest.record_feature("success")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    wf._root.attribute("user_language", lang)
    wf._root.attribute("response_char_count", len(final_output))
    wf._root.attribute("tools_invoked_count", len(manifest.tools_picked))
    wf._root.attribute("retry_count", len(manifest.tools_picked))
    wf._root.attribute("success", True)
    wf._root.attribute("latency_ms", elapsed_ms)

    manifest.log.feature_set(name="user_language", value=lang)
    manifest.log.feature_set(name="response_char_count", value=len(final_output))
    manifest.log.feature_set(name="tools_invoked_count", value=len(manifest.tools_picked))

    ix_count = 1 + 1 + 1 + len(manifest.tools_picked)
    manifest.interaction_count = ix_count
    manifest.expected_span_count = ix_count
    manifest.per_ix_expected_span_count = [ix_count]
    manifest.log.interaction_end(index=0)
    return final_output


def run_simulation(
    client: Client,
    *,
    case: SimCase,
    seed: int | None = None,
    conversation_id: str | None = None,
    flush_mode: str = "process",
    local_only: bool = False,
) -> tuple[dict[str, Any], RunManifest]:
    rng = random.Random(seed)
    conv = conversation_id or f"sim-{case.case_id}-{uuid4().hex[:12]}"
    manifest = RunManifest(seed=seed, case_id=case.case_id, conversation_id=conv)

    lang = case.user_language or rng.choice(["en", "es", "fr"])
    manifest.user_language = lang

    task = case.user_task_es if lang == "es" and case.user_task_es else case.user_task_en
    hint = f"seed={seed}, lang={lang}, case={case.case_id}"
    user_message = build_user_message(hint=hint, task=task)

    workflow_name = case.case_id.replace("_", " ").title()

    with client.session(conv):
        with client.workflow(name=workflow_name, input=user_message) as wf:
            final_output = _run_workflow_body(
                wf, case=case, manifest=manifest, rng=rng, user_text=user_message, lang=lang
            )
            if case.multi_interaction:
                with wf.interaction(name="Follow-up Step", primitive=GENERATION, parent=wf._root) as fu_ix:
                    fu_ix.input = "Execute the planned tool step and report a one-line result."
                    fu_ix.event("followup_started")
                    fu_ix.output = "follow-up complete"
                manifest.interaction_count += 1
                manifest.expected_span_count += 1
            wf.output = final_output

    manifest.wire_payload = wf.to_validate_payload()

    if local_only:
        return {
            "accepted": True,
            "local_only": True,
            "interactions": manifest.wire_payload.get("interactions"),
        }, manifest

    if str(flush_mode).strip().lower() == "ingest":
        result = wf.flush_ingest()
    else:
        result = wf.flush_process()
    return result, manifest
