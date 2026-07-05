export enum Instruments {
  OPENAI = "openai",
  ANTHROPIC = "anthropic",
  GEMINI = "gemini",
}

export const ALL_INSTRUMENTS = new Set<Instruments>([
  Instruments.OPENAI,
  Instruments.ANTHROPIC,
  Instruments.GEMINI,
]);

function coerceOne(value: Instruments | string): Instruments {
  if (typeof value !== "string") return value;
  const key = value.trim().toLowerCase();
  const match = Object.values(Instruments).find((v) => v === key);
  if (!match) {
    throw new Error(
      `unknown instrument ${JSON.stringify(value)}; expected one of ${Object.values(Instruments).join(", ")}`,
    );
  }
  return match;
}

function coerceSet(values: Iterable<Instruments | string> | null | undefined): Set<Instruments> {
  if (!values) return new Set();
  return new Set([...values].map(coerceOne));
}

export function resolveInstruments(options: {
  instruments?: Iterable<Instruments | string> | null;
  blockInstruments?: Iterable<Instruments | string> | null;
  autoInstrument?: boolean;
  providers?: Iterable<string> | null;
}): Set<Instruments> {
  if (options.autoInstrument === false) return new Set();

  let allow: Set<Instruments>;
  if (options.instruments != null) {
    allow = coerceSet(options.instruments);
  } else if (options.providers != null) {
    allow = coerceSet(options.providers);
  } else {
    allow = new Set(ALL_INSTRUMENTS);
  }

  const blocked = coerceSet(options.blockInstruments);
  return new Set([...allow].filter((i) => !blocked.has(i)));
}
