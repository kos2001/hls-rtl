import type {
  ChatResponse,
  EquivResult,
  GraphResult,
  Health,
  Progressive,
  QoRReport,
  Reflection,
  SignoffReport,
  Telemetry,
  VerificationResults,
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

  chat: (message: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
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
}
