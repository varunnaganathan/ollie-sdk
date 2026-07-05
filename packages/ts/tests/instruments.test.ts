import { describe, expect, it } from "vitest";

import { Instruments, resolveInstruments } from "../src/instruments.js";

describe("resolveInstruments", () => {
  it("returns empty when autoInstrument is false", () => {
    expect(resolveInstruments({ autoInstrument: false })).toEqual(new Set());
  });

  it("allowlists instruments", () => {
    expect(resolveInstruments({ instruments: [Instruments.OPENAI] })).toEqual(
      new Set([Instruments.OPENAI]),
    );
  });

  it("blocks instruments", () => {
    expect(
      resolveInstruments({
        blockInstruments: [Instruments.OPENAI],
      }),
    ).toEqual(new Set([Instruments.ANTHROPIC, Instruments.GEMINI]));
  });
});
