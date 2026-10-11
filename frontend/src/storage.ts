/** Preferences must not prevent the workspace from opening in private mode. */
export function readPreference(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback } catch { return fallback }
}

export function writePreference(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* Storage can be disabled. */ }
}
