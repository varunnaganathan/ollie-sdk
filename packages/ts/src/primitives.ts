export const EXTERNAL_INTERACTION = "external_interaction";
export const DELEGATION = "delegation";
export const STATE_MUTATION = "state_mutation";
export const VERIFICATION = "verification";
export const GENERATION = "generation";

export const BUILTIN_PRIMITIVES = new Set([
  EXTERNAL_INTERACTION,
  DELEGATION,
  STATE_MUTATION,
  VERIFICATION,
  GENERATION,
]);

export function isValidPrimitive(value: string): boolean {
  return BUILTIN_PRIMITIVES.has(value);
}
