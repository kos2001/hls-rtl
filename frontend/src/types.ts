export interface Health {
  ok: boolean
  model: string
  has_key: boolean
  verilator: boolean
  gateway_base_url: string
}

export interface PatternResult {
  name: string
  pixels: number
  status: 'pass' | 'fail'
  mismatches: number
  golden_sha256: string
  rtl_sha256: string
  sc_sha256: string | null
}

export interface VerificationResults {
  schema_version: string
  source: string
  design: { module: string; pixel_w: number; lut_depth: number }
  gammas: Record<string, number>
  summary: {
    total_patterns: number
    passed: number
    failed: number
    total_pixels: number
  }
  patterns: PatternResult[]
}

export interface ChatResponse {
  content: string
  user_id: string
}

export interface QoRCheck {
  id: string
  severity: 'error' | 'warn' | 'info'
  ok: boolean
  detail: string
}

export interface QoRReport {
  module: string | null
  score: number
  grade: string
  lint_tool: string
  metrics: {
    lint_pass: boolean | null
    synthesizable?: boolean
    synth_flops?: number
    synth_cells?: number
    synth_latches?: number
    reset_kind: string
    reset_active: string
    hdl_dialect: string
    [k: string]: unknown
  }
  checks: QoRCheck[]
}

export interface SignoffStage {
  name: string
  status: 'pass' | 'fail' | 'skip'
  gating: boolean
  detail: string
}

export interface SignoffReport {
  verdict: 'SIGNED_OFF' | 'CONDITIONAL' | 'REJECTED'
  score: number
  grade: string
  module: string | null
  stages: SignoffStage[]
}

export interface Telemetry {
  kind: string
  count: number
  verdicts?: Record<string, number>
  mean_score?: number
  last_score?: number
  history?: { ts: number; verdict: string | null; score: number | null }[]
}

export interface ProgressiveRep {
  name: string
  role: string
  overall: string
  patterns: { name: string; status: string; golden_sha256: string }[]
}

export interface Progressive {
  patterns_total: number
  bit_exact: boolean
  representations: ProgressiveRep[]
  note: string
}

export interface Reflection {
  ok: boolean
  root_stage: string | null
  error_source?: string
  diagnosis?: string
  action?: string
  downstream_symptoms?: string[]
  skipped?: string[]
}

export interface EquivResult {
  equivalent: boolean
  available: boolean
  status: string
  issues: string[]
  log_tail?: string
}

export interface GraphResult {
  available: boolean
  result?: string
  error?: string
}
