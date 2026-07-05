export const LANGUAGE_CONTEXT = new Set([
  "llm_error",
  "tool_error",
  "used_tool",
  "high_latency",
  "output_truncated",
  "safety_stop",
  "tool_loop",
  "runtime_failure",
  "empty_final_response",
]);

export const LANGUAGE_TRIGGER = new Set(["repeated_tool_error"]);

export const AISDK_CONTEXT = new Set([
  "llm_empty_output",
  "llm_empty_input",
  "llm_provider_error_rate",
  "llm_token_blowup",
  "io_error_in_output",
]);

export const ALL_CONTEXT = new Set([...LANGUAGE_CONTEXT, ...AISDK_CONTEXT]);
export const ALL_TRIGGER = LANGUAGE_TRIGGER;
export const ALL_SIGNALS = new Set([...ALL_CONTEXT, ...ALL_TRIGGER]);
