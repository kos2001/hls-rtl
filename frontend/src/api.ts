import type {
  ChatResponse,
  EquivResult,
  GraphResult,
  Health,
  Progressive,
  QoRReport,
  Reflection,
  Schematic,
  SignoffReport,
  SkillReport,
  Telemetry,
  VerificationResults,
  WaveStatus,
  Waveform,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = body?.detail ?? JSON.stringify(body)
    } catch {
      detail = await res.text()
    }
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ''}`)
  }
  return (await res.json()) as T
}

export const api = {
  health: () => request<Health>('/health'),

  /**
   * Verification results from the api-server. Falls back to the bundled
   * static snapshot (public/results.json) when the backend is unreachable,
   * so the dashboard still renders offline.
   */
  verification: async (): Promise<VerificationResults> => {
    try {
      return await request<VerificationResults>('/verification')
    } catch {
      const res = await fetch('/results.json')
      if (!res.ok) throw new Error('backend unreachable and no bundled results.json')
      return (await res.json()) as VerificationResults
    }
  },

  analyze: () => request<QoRReport>('/analyze'),

  signoff: (runRegression: boolean) =>
    request<SignoffReport>('/signoff', {
      method: 'POST',
      body: JSON.stringify({ run_regression: runRegression }),
    }),

  telemetry: (kind: string) => request<Telemetry>(`/telemetry/${kind}`),

  // `session`: per-conversation id — same id keeps transcript continuity on
  // the gateway, a new id starts a fresh session (no stale design memory).
  chat: (message: string, session?: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session }),
    }),

  plan: (uarch: string, algorithm: string) =>
    request<{ plan: string }>('/plan', {
      method: 'POST',
      body: JSON.stringify({ uarch, algorithm }),
    }),

  progressive: (runRegression: boolean) =>
    request<Progressive>('/progressive', {
      method: 'POST',
      body: JSON.stringify({ run_regression: runRegression }),
    }),

  segments: () => request<{ count: number; segments: unknown[] }>('/segments'),

  reflect: (stages?: Record<string, string>) =>
    request<Reflection>('/reflect', {
      method: 'POST',
      body: JSON.stringify(stages ? { stages } : {}),
    }),

  // Omit `new` to self-equiv the project RTL (sanity), else prove candidate ≡ project.
  equiv: (newCode?: string) =>
    request<EquivResult>('/equiv', {
      method: 'POST',
      body: JSON.stringify(newCode && newCode.trim() ? { new: newCode } : {}),
    }),

  graphExplain: (node: string) =>
    request<GraphResult>(`/graph/explain?node=${encodeURIComponent(node)}`),

  // Which skills the gateway's serving profile really has. `refresh` re-scans
  // after a sync instead of serving the cached report.
  skills: (refresh = false) =>
    request<SkillReport>(`/skills${refresh ? '?refresh=true' : ''}`),

  waveStatus: () => request<WaveStatus>('/waveform/status'),

  // Runs the traced (WAVES=1) regression when no dump exists; ~30% slower sim.
  waveRun: (regenerate: boolean) =>
    request<WaveStatus>('/waveform/run', {
      method: 'POST',
      body: JSON.stringify({ regenerate }),
    }),

  waveform: (opts: { start?: number; end?: number; maxTransitions?: number } = {}) => {
    const q = new URLSearchParams()
    if (opts.start != null) q.set('start', String(opts.start))
    if (opts.end != null) q.set('end', String(opts.end))
    q.set('max_transitions', String(opts.maxTransitions ?? 20000))
    return request<Waveform>(`/waveform?${q}`)
  },

  schematic: () => request<Schematic>('/schematic'),
}
