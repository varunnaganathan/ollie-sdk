export const __version__ = "0.2.0";

export function utcNowIso(): string {
  return new Date().toISOString();
}
