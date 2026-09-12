import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { renderMD } from './md'
import { log, traced } from './log'
import { Busy, useElapsed } from './ui'
import { Citations } from './Knowledge'
import type { KbChunk, SkillReport } from './types'

const AGENT_HINT = 'agent loop can take ~30-60s'

// ---------- Plan: parse numbered steps with NEW/MODIFIED/UNCHANGED tags ----------
interface PlanStep {
  n: number
  tag: 'NEW' | 'MODIFIED' | 'UNCHANGED' | null
  title: string
  body: string
}

// The planner is instructed to use English tags, but tolerate Korean ones too.
const TAG_MAP: Record<string, PlanStep['tag']> = {
  NEW: 'NEW', 신규: 'NEW', 추가: 'NEW',
  MODIFIED: 'MODIFIED', 변경: 'MODIFIED', 수정: 'MODIFIED',
  UNCHANGED: 'UNCHANGED', 유지: 'UNCHANGED', 불변: 'UNCHANGED', 무변경: 'UNCHANGED',
}
const TAG_ALT = Object.keys(TAG_MAP).join('|')

function parsePlan(plan: string): PlanStep[] {
  // Steps look like: "3. MODIFIED: FIFO controller" or "3. 변경: FIFO 컨트롤러"
  const re = new RegExp(`^(\\d+)\\.\\s+(?:(${TAG_ALT})\\s*:\\s*)?(.*)$`)
  const steps: PlanStep[] = []
  let cur: PlanStep | null = null
  for (const line of plan.split('\n')) {
    const m = re.exec(line.trim())
    // `cur` is not pushed until the next header, so the number of steps seen
    // so far is steps.length + (cur ? 1 : 0). Accept the first header with any
    // number; after that require strict sequence (so numbered sub-lists inside
    // a body don't split steps).
    const seen = steps.length + (cur ? 1 : 0)
    if (m && (seen === 0 || Number(m[1]) === seen + 1)) {
      if (cur) steps.push(cur)
      cur = {
        n: Number(m[1]),
        tag: m[2] ? TAG_MAP[m[2]] : null,
        title: m[3] || '(untitled step)',
        body: '',
      }
    } else if (cur) {
      cur.body += (cur.body ? '\n' : '') + line
    }
  }
  if (cur) steps.push(cur)
  return steps
}

function StepCard({ step }: { step: PlanStep }) {
  const [open, setOpen] = useState(true)
  return (
    <div className={`step-card ${step.tag ? `step-${step.tag}` : ''}`}>
      <button className="step-head" onClick={() => setOpen(!open)}>
        <span className="step-num">{step.n}</span>
        {step.tag && <span className={`tag tag-${step.tag}`}>{step.tag}</span>}
        <span className="step-title">{step.title}</span>
        <span className="step-chevron">{open ? '▾' : '▸'}</span>
      </button>
      {open && step.body.trim() && <div className="step-body">{renderMD(step.body.trim())}</div>}
    </div>
  )
}

const PLAN_LEGEND: [PlanStep['tag'], string][] = [
  ['NEW', 'newly added'],
  ['MODIFIED', 'changed vs existing'],
  ['UNCHANGED', 'kept as-is'],
]

export function PlanTab({ gatewayReady }: { gatewayReady: boolean }) {
  const [uarch, setUarch] = useState(
    '8-bit per-channel gamma LUT, 1 px/cycle, ready/valid handshake.\nCHANGED: add a 2-deep skid buffer for backpressure.',
  )
  const [algo, setAlgo] = useState('out = lut[in] per channel')
  const [plan, setPlan] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const sec = useElapsed(busy)

  async function generate() {
    setBusy(true); setErr(null); setPlan(null)
    const r = await traced(
      { stage: 'plan', tool: 'hermes-gateway', design: 'gamma', cmd: 'plan --uarch --algorithm' },
      () => api.plan(uarch, algo),
      (v) => {
        log.info('PLAN', `${v.plan.split('\n').length} lines returned`)
        return { status: 'pass' }
      },
    ).catch(() => null)
    if (r) setPlan(r.plan)
    else setErr('planner call failed — see the transcript for the error')
    setBusy(false)
  }

  const steps = plan ? parsePlan(plan) : []
  const counts = steps.reduce<Record<string, number>>((a, s) => {
    if (s.tag) a[s.tag] = (a[s.tag] ?? 0) + 1
    return a
  }, {})

  return (
    <div className="plan-grid">
      <section className="card plan-inputs">
        <h2>Plan from uArch + Algorithm</h2>
        <p className="muted small">
          Reasoning module: uArch (existing + changed) + Python algorithm → step-by-step
          implementation plan, each step tagged for incremental regeneration.
          한글로 입력하면 한글 플랜이 생성됩니다 (태그는 NEW/MODIFIED/UNCHANGED 유지).
          {!gatewayReady && ' Requires the Hermes Gateway key.'}
        </p>
        <label className="fld-label">uArch document (existing + changed)</label>
        <textarea value={uarch} onChange={(e) => setUarch(e.target.value)} rows={7} />
        <label className="fld-label">Algorithm reference (Python golden)</label>
        <textarea value={algo} onChange={(e) => setAlgo(e.target.value)} rows={3} />
        <div className="chat-actions">
          <button onClick={generate} disabled={busy || !uarch.trim()}>
            {busy ? 'Planning…' : 'Generate plan'}
          </button>
        </div>
        {busy && <Busy label="Planner running via Hermes Gateway" sec={sec} hint={AGENT_HINT} />}
        {err && <pre className="chat-error">{err}</pre>}
      </section>

      <section className="card plan-result">
        <div className="plan-result-head">
          <h2>Implementation plan</h2>
          {steps.length > 0 && (
            <div className="pill-row">
              {PLAN_LEGEND.filter(([t]) => counts[t as string]).map(([t]) => (
                <span key={t} className={`tag tag-${t}`}>{counts[t as string]} {t}</span>
              ))}
            </div>
          )}
        </div>
        {!plan && !busy && (
          <p className="muted small">No plan yet — describe the uArch change and generate.</p>
        )}
        {steps.length > 0 && (
          <div className="steps">{steps.map((s) => <StepCard key={s.n} step={s} />)}</div>
        )}
        {plan && steps.length === 0 && (
          /* fallback: unstructured plan text, still markdown-rendered */
          <div className="md-block">{renderMD(plan)}</div>
        )}
      </section>
    </div>
  )
}

// ---------- Ask: conversation bubbles with markdown ----------
interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  /** Grounding passages for this reply, so the answer can be checked. */
  citations?: KbChunk[]
}

export function ChatPanel({ gatewayReady, skills }:
  { gatewayReady: boolean; skills?: SkillReport | null }) {
  const [message, setMessage] = useState('')
  const [history, setHistory] = useState<ChatMsg[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // One gateway session per conversation; "Clear" rotates it so a new
  // conversation never inherits stale design facts from the old transcript.
  const [session, setSession] = useState(() => crypto.randomUUID())
  const sec = useElapsed(busy)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [history, busy])

  async function send() {
    const q = message.trim()
    if (!q || busy) return
    setBusy(true); setError(null); setMessage('')
    setHistory((h) => [...h, { role: 'user', content: q }])
    const res = await traced(
      { stage: 'assistant', tool: 'hermes-gateway', design: 'gamma',
        cmd: `chat --session ${session.slice(0, 8)} "${q.slice(0, 60)}${q.length > 60 ? '…' : ''}"` },
      () => api.chat(q, session),
      (v) => ({ status: 'pass', extra: `${v.content.length} chars` }),
    ).catch(() => null)
    if (res) setHistory((h) => [...h,
      { role: 'assistant', content: res.content, citations: res.citations }])
    else setError('gateway call failed — see the transcript for the error')
    setBusy(false)
  }

  return (
    <section className="card chat">
      <div className="signoff-head">
        <h2>Ask Hermes</h2>
        {history.length > 0 && (
          <button className="btn-ghost"
            onClick={() => { setHistory([]); setError(null); setSession(crypto.randomUUID()) }}>
            Clear (new session)
          </button>
        )}
      </div>
      <p className="muted small">
        Answers are grounded in the retrieved knowledge base (see the Knowledge tab);
        every reply lists the passages behind it.{' '}
        RTL-assistant via the Hermes Gateway
        {skills?.active.length
          ? <>, grounded in {skills.active.length} loaded skill
              {skills.active.length > 1 ? 's' : ''} (<code>{skills.active.join(' · ')}</code>)</>
          : ', with no agent skills loaded'}.
        {skills?.missing.length
          ? ` ${skills.missing.length} wanted skill(s) are not installed in profile ${skills.profile} — run scripts/sync_hermes_skills.py.`
          : ''}
        {!gatewayReady && ' Set HERMES_GATEWAY_API_KEY to enable.'}
      </p>

      {history.length > 0 && (
        <div className="chat-log">
          {history.map((m, i) => (
            <div key={i} className={`bubble bubble-${m.role}`}>
              <div className="bubble-role">{m.role === 'user' ? 'you' : 'hermes'}</div>
              <div className="bubble-body">
                {m.role === 'assistant' ? renderMD(m.content) : m.content}
              </div>
              {m.citations?.length ? <Citations items={m.citations} /> : null}
            </div>
          ))}
          {busy && (
            <div className="bubble bubble-assistant">
              <div className="bubble-role">hermes</div>
              <Busy label="thinking" sec={sec} hint={AGENT_HINT} />
            </div>
          )}
          <div ref={endRef} />
        </div>
      )}

      {error && <pre className="chat-error">{error}</pre>}
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="e.g. Explain the ready/valid handshake of the gamma DUT. / 예: gamma DUT의 스키드 버퍼 동작을 설명해 줘. (한글 질문 → 한글 답변)"
        rows={3}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }}
      />
      <div className="chat-actions">
        <button onClick={send} disabled={busy || !message.trim()}>
          {busy ? 'Asking…' : 'Send  (⌘/Ctrl+Enter)'}
        </button>
      </div>
    </section>
  )
}
