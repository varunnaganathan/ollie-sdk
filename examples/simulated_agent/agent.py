from __future__ import annotations

import random
import time
from typing import Any
from uuid import uuid4

from simulated_agent.cases import SimCase
from simulated_agent.expectations import RunManifest
from simulated_agent.llm import complete, confidence_band
from simulated_agent.prompts import build_user_message
from simulated_agent.tools import dispatch_tool, pick_tools

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ollie.client import Client


def _run_single_interaction(
    trace,
    *,
    case: SimCase,
    manifest: RunManifest,
    rng: random.Random,
    source: str,
    target: str,
    user_text: str,
    lang: str,
    ix_index: int = 0,
) -> str:
    manifest.log.interaction_start(index=ix_index, source=source, target=target)
    final_output = ""
    tool_results: list[str] = []

    with trace.interaction(
        source=source,
        target=target,
        input=user_text,
        output="",
    ) as ix:
        started = time.perf_counter()

        with ix.span("llm_call", name="openai.chat") as llm_ctx:
            manifest.log.span_start(kind="llm_call", name="openai.chat")
            llm_ctx.payload["phase"] = "pre"
            llm_text, model_name = complete(user_message=user_text)
            llm_ctx.payload.update(
                {
                    "phase": "post",
                    "model": model_name,
                    "response_len": len(llm_text),
                }
            )
            manifest.record_feature("llm_response_char_count")
            ix.feature("llm_response_char_count", len(llm_text))
            manifest.log.feature_set(name="llm_response_char_count", value=len(llm_text))

            band = confidence_band(len(llm_text))
            manifest.record_feature("agent_confidence_band")
            ix.feature("agent_confidence_band", band)
            manifest.log.feature_set(name="agent_confidence_band", value=band)

            ix.feature("model_family", model_name.split("-")[0] if model_name else "openai")
            manifest.log.span_end(kind="llm_call", name="openai.chat")
            manifest.span_kinds.append("llm_call")

        tools = pick_tools(rng, min_tools=case.min_tools, max_tools=case.max_tools)
        if ix_index == 0:
            manifest.tools_picked = list(tools)
        manifest.per_ix_tools_picked.append(list(tools))

        with ix.span("tool_dispatch") as _dispatch_ctx:
            manifest.log.span_start(kind="tool_dispatch")
            manifest.span_kinds.append("tool_dispatch")
            _dispatch_ctx.payload["tool_count"] = len(tools)

            for tool_name in tools:
                with ix.span("tool_call", name=tool_name) as tool_ctx:
                    manifest.log.span_start(kind="tool_call", name=tool_name)
                    manifest.span_kinds.append("tool_call")
                    manifest.span_names.append(tool_name)
                    tool_ctx.payload["tool"] = tool_name
                    result, payload = dispatch_tool(tool_name, rng)
                    tool_ctx.payload.update(payload)
                    tool_ctx.payload["result_preview"] = result[:80]
                    tool_results.append(result)
                    manifest.record_feature("last_tool_result_size")
                    ix.feature("last_tool_result_size", len(result))
                    manifest.log.feature_set(name="last_tool_result_size", value=len(result))
                    manifest.log.span_end(kind="tool_call", name=tool_name)

            manifest.log.span_end(kind="tool_dispatch")

        final_output = llm_text
        if tool_results:
            final_output = f"{llm_text} | tools: {', '.join(tool_results)}"

        ix.output = final_output
        manifest.record_feature("user_language")
        ix.feature("user_language", lang)
        manifest.log.feature_set(name="user_language", value=lang)

        manifest.record_feature("response_char_count")
        ix.feature("response_char_count", len(final_output))
        manifest.log.feature_set(name="response_char_count", value=len(final_output))

        manifest.record_feature("tools_invoked_count")
        ix.feature("tools_invoked_count", len(tools))
        manifest.log.feature_set(name="tools_invoked_count", value=len(tools))

        ix.feature("retry_count", len(tools))
        ix.feature("success", True)
        manifest.record_feature("retry_count")
        manifest.record_feature("success")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        ix.feature("latency_ms", elapsed_ms)

    ix_span_count = 1 + 1 + len(tools)  # llm_call + tool_dispatch + tool_calls
    manifest.log.interaction_end(index=ix_index)
    manifest.interaction_count += 1
    manifest.per_ix_expected_span_count.append(ix_span_count)
    manifest.expected_span_count += ix_span_count
    return final_output


def run_simulation(
    client: Client,
    *,
    case: SimCase,
    seed: int | None = None,
    conversation_id: str | None = None,
    flush_mode: str = "process",
) -> tuple[dict[str, Any], RunManifest]:
    rng = random.Random(seed)
    conv = conversation_id or f"sim-{case.case_id}-{uuid4().hex[:12]}"
    manifest = RunManifest(seed=seed, case_id=case.case_id, conversation_id=conv)

    lang = case.user_language or rng.choice(["en", "es", "fr"])
    manifest.user_language = lang

    task = case.user_task_es if lang == "es" and case.user_task_es else case.user_task_en
    hint = f"seed={seed}, lang={lang}, case={case.case_id}"
    user_message = build_user_message(hint=hint, task=task)

    trace = client.trace(conversation_id=conv)

    if not case.multi_interaction:
        _run_single_interaction(
            trace,
            case=case,
            manifest=manifest,
            rng=rng,
            source="user",
            target="agent",
            user_text=user_message,
            lang=lang,
            ix_index=0,
        )
    else:
        _run_single_interaction(
            trace,
            case=case,
            manifest=manifest,
            rng=rng,
            source="user",
            target="agent",
            user_text=user_message,
            lang=lang,
            ix_index=0,
        )
        followup = "Execute the planned tool step and report a one-line result."
        _run_single_interaction(
            trace,
            case=case,
            manifest=manifest,
            rng=rng,
            source="agent",
            target="tool_executor",
            user_text=followup,
            lang=lang,
            ix_index=1,
        )
        # Set parent_interaction_ref on second interaction in trace buffer
        if len(trace._interactions) >= 2:
            trace._interactions[1]["parent_interaction_ref"] = "0"

    manifest.wire_payload = trace.to_validate_payload()
    if str(flush_mode).strip().lower() == "ingest":
        result = trace.flush_ingest()
    else:
        result = trace.flush_process()
    return result, manifest
