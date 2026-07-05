import { Instruments } from "../instruments.js";

let installed = false;
let captureContent = true;
let active: Set<Instruments> = new Set();

export function getTracingState() {
  return { installed, captureContent, active };
}

export function setTracingState(options: {
  installed?: boolean;
  captureContent?: boolean;
  active?: Set<Instruments>;
}) {
  if (options.installed !== undefined) installed = options.installed;
  if (options.captureContent !== undefined) captureContent = options.captureContent;
  if (options.active !== undefined) active = options.active;
}

export function isTracingInstalled(): boolean {
  return installed;
}

export function activeInstruments(): Set<Instruments> {
  return new Set(active);
}

export function getCaptureContent(): boolean {
  return captureContent;
}
