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
  /** Knowledge-base passages injected as grounding for this answer. */
  citations?: KbChunk[]
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

// ---------- Hermes skills (what the gateway profile can actually load) ----------
export interface SkillInfo {
  name: string
  category: string
  description: string
  installed: boolean
  source: 'profile' | 'repo-only' | 'missing'
  purpose: string
}

export interface SkillReport {
  profile: string | null
  profile_dir: string | null
  gateway_base_url: string
  use_skills: boolean
  active: string[]
  missing: string[]
  skills: SkillInfo[]
}

// ---------- Waveform ----------
export interface WaveSignal {
  name: string
  width: number
  kind: string
  scope: string
  /** [time, value] — value is '0'|'1'|'x'|'z' for width 1, else a bit string. */
  transitions: [number, string][]
}

export interface WaveParam {
  name: string
  width: number
  value: string
}

export interface Waveform {
  available: boolean
  /** Elaboration constants, listed rather than plotted. */
  parameters?: WaveParam[]
  error?: string
  scope?: string
  scopes?: { name: string; signals: number }[]
  timescale_seconds?: number
  time_unit?: string
  start?: number
  end?: number
  truncated?: boolean
  transition_count?: number
  signals?: WaveSignal[]
}

export interface WaveStatus {
  available: boolean
  path: string
  size_bytes?: number
  modified?: number
  ran?: boolean
  ok?: boolean
  error?: string
  log_tail?: string
}

// ---------- Schematic ----------
export interface SchematicNode {
  id: string
  label: string
  kind: 'port' | 'cell'
  cls: string
  layer: number
  width: number
  type?: string
  name?: string
  src_line?: number | null
  direction?: 'input' | 'output'
  seq?: boolean
}

export interface SchematicEdge {
  from: string
  to: string
  net: string
  width: number
}

export interface Schematic {
  available: boolean
  error?: string
  top?: string
  node_count?: number
  edge_count?: number
  layers?: number
  truncated?: boolean
  stats?: Record<string, number>
  nodes?: SchematicNode[]
  edges?: SchematicEdge[]
  note?: string
}

// ---------- Knowledge base ----------
export interface KbChunk {
  id: string
  source: string
  kind: 'verilog' | 'python' | 'cpp' | 'markdown' | 'live'
  title: string
  citation: string
  pinned: boolean
  chars: number
  score?: number | null
  text?: string
}

export interface KbStats {
  chunks: number
  pinned: number
  terms: number
  avg_chunk_tokens: number
  sources: Record<string, number>
  built_at: number
  retrieval: string
}

export interface KbSearch {
  query: string
  count: number
  results: KbChunk[]
}

// ---------- uArch spec ----------
export interface Uarch {
  path: string
  chars: number
  /** Sections 1-8: the stable spec, shown read-only. */
  spec: string
  /** Section 9, where a proposal goes. */
  changed_section: string
}

export interface DocFile {
  name: string
  path: string
  chars: number
  text: string
  /** Language actually served — may be 'en' even when 'ko' was asked for. */
  lang?: string
  translated?: boolean
}

// ---------- Self-improvement loop ----------
export interface PatternOutcome {
  name: string
  ok: boolean
  pixels: number
  sha256: string
  first_bad_index: number | null
  got: string
  ref: string
  differing: number
}

export interface Proof {
  candidate_path: string
  verdict: 'PROVEN' | 'REJECTED' | 'INCONCLUSIVE'
  equivalent: boolean
  stages: Record<string, string>
  details: Record<string, string>
  tests: { total: number; passed: number; failed: number }
  elapsed_s: number
  patterns: PatternOutcome[]
  throughput: Record<string, number>
  proves: string
  does_not_prove: string
  log_tail: string
}

export interface EvidenceGap {
  gap: string
  severity: 'high' | 'medium' | 'low'
  why_it_matters: string
  how_to_close: string
  tool_installed: boolean
}

export interface Audit {
  gaps: EvidenceGap[]
  note: string
}

export interface LoopAttempt {
  iteration: number
  proof?: Proof
  diff?: { added: number; removed: number; unified: string }
  changed_rtl?: boolean
  reflection?: Reflection
  note?: string
  error?: string
  citations?: KbChunk[]
}

export type LoopOutcome =
  | 'PROVEN_CHANGE' | 'ORACLE_CONFLICT' | 'NO_CHANGE' | 'EXHAUSTED' | 'ERRORED'

export interface LoopResult {
  ok: boolean
  error?: string
  goal: string
  iterations_run: number
  max_iters: number
  baseline: Proof
  attempts: LoopAttempt[]
  outcome: LoopOutcome
  summary: string
  converged: boolean
  proven_candidate: string | null
  proves: string
  does_not_prove: string
  note: string
}

// ---------- Mutation coverage ----------
export interface MutantResult {
  id: string
  operator: string
  description: string
  line: number
  before: string
  after: string
  caught: boolean
  caught_by: string | null
  detail: string
  elapsed_s: number
}

export interface MutationRun {
  total_available: number
  run: number
  caught: number
  survived: number
  score: number
  caught_by_stage: Record<string, number>
  operators: string[]
  results: MutantResult[]
  note: string
}
