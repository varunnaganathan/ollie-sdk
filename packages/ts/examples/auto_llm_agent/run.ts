#!/usr/bin/env tsx
import { assertAutoCapture, printTree, runAutoAgent, type Provider } from "./agent.js";

function parseArgs(argv: string[]) {
  let provider: Provider = "openai";
  let printTreeFlag = false;
  let validate = false;
  let localOnly = true;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--provider" && argv[i + 1]) provider = argv[++i] as Provider;
    else if (arg === "--print-tree") printTreeFlag = true;
    else if (arg === "--validate") validate = true;
    else if (arg === "--no-local-only") localOnly = false;
  }
  return { provider, printTreeFlag, validate, localOnly };
}

async function main() {
  const { provider, printTreeFlag, validate, localOnly } = parseArgs(process.argv.slice(2));
  const [result, wire] = await runAutoAgent({ provider, localOnly });
  if (printTreeFlag) console.log(printTree(wire));
  if (validate) assertAutoCapture(wire, provider);
  console.log(JSON.stringify({ result, interaction_count: (wire.interactions as unknown[])?.length }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
