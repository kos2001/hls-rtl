import { useEffect, useState } from 'react'
import { api } from './api'
import { ChatPanel, PlanTab } from './PlanAsk'
import { Busy, Sparkline, useElapsed } from './ui'
import type {
  EquivResult,
  Health,
  PatternResult,
  Progressive,
  QoRReport,
  Reflection,
  SignoffReport,
  Telemetry,
  VerificationResults,
} from './types'

// ---------- small shared bits ----------
function Sha({ value }: { value: string | null }) {
  if (!value) return <span className="sha sha-none">— skipped</span>
  return <span className="sha" title={value}>{value.slice(0, 12)}…</span>
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === 'pass' ? 'pass' : status === 'fail' ? 'fail' : 'skip'
  return <span className={`badge badge-${cls}`}>{status}</span>
}

function HealthPill({ health }: { health: Health | null }) {
  if (!health) return <span className="pill pill-warn">backend: connecting…</span>
  return (
    <div className="pill-row">
      <span className="pill pill-ok">api: online</span>
      <span className={`pill ${health.verilator ? 'pill-ok' : 'pill-warn'}`}>
        verilator: {health.verilator ? 'yes' : 'no'}
      </span>
      <span className={`pill ${health.has_key ? 'pill-ok' : 'pill-warn'}`}>
        hermes: {health.has_key ? 'connected' : 'no key'}
      </span>
      <span className="pill pill-muted" title={health.gateway_base_url}>{health.model}</span>
    </div>
  )
}

// ---------- Verify tab ----------
function VerifyTab({ data, qor, telemetry, onSignoff }:
  { data: VerificationResults; qor: QoRReport | null; telemetry: Telemetry | null; onSignoff: () => void }) {
  const allPass = data.summary.failed === 0
  return (
    <>
      <section className="cards">
        <div className={`card stat ${allPass ? 'stat-ok' : 'stat-fail'}`}>
          <div className="stat-value">{allPass ? 'PASS' : 'FAIL'}</div>
          <div className="stat-label">overall</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{data.summary.passed}/{data.summary.total_patterns}</div>
          <div className="stat-label">patterns passing</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{data.summary.total_pixels.toLocaleString()}</div>
          <div className="stat-label">pixels verified</div>
        </div>
        <div className="card stat">
          <div className="stat-value">{data.design.module} · {data.design.pixel_w}b</div>
          <div className="stat-label">LUT {data.design.lut_depth} · γ {Object.values(data.gammas).join('/')}</div>
        </div>
      </section>

      <section className="card">
        <h2>Patterns</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>pattern</th><th className="num">pixels</th><th>status</th>
                <th className="num">mism.</th><th>golden sha-256</th><th>rtl sha-256</th><th>systemc</th></tr>
            </thead>
            <tbody>
              {data.patterns.map((p: PatternResult) => (
                <tr key={p.name}>
                  <td className="mono">{p.name}</td>
                  <td className="num">{p.pixels.toLocaleString()}</td>
                  <td><StatusBadge status={p.status} /></td>
                  <td className="num">{p.mismatches}</td>
                  <td><Sha value={p.golden_sha256} /></td>
                  <td><Sha value={p.rtl_sha256} /></td>
                  <td><Sha value={p.sc_sha256} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">{data.source}</p>
      </section>

      <QoRCard qor={qor} />
      <SignoffPanel telemetry={telemetry} onRun={onSignoff} />
    </>
  )
}

function QoRCard({ qor }: { qor: QoRReport | null }) {
  if (!qor) return null
  const m = qor.metrics
  return (
    <section className="card">
      <h2>Design Quality (QoR)</h2>
      <div className="qor-head">
        <div className={`grade grade-${qor.grade}`}>{qor.grade}</div>
        <div>
          <div className="stat-value">{qor.score}/100</div>
          <div className="muted small">lint: {qor.lint_tool} · {m.hdl_dialect} · {m.reset_kind}/{m.reset_active} reset</div>
        </div>
        <div className="qor-metrics">
          <span className="pill pill-muted">flops {m.synth_flops ?? '—'}</span>
          <span className="pill pill-muted">cells {m.synth_cells ?? '—'}</span>
          <span className={`pill ${m.synth_latches ? 'pill-warn' : 'pill-ok'}`}>latches {m.synth_latches ?? '—'}</span>
          <span className={`pill ${m.synthesizable ? 'pill-ok' : 'pill-warn'}`}>{m.synthesizable ? 'synthesizes' : 'unsynth'}</span>
        </div>
      </div>
      <div className="checks">
        {qor.checks.map((c) => (
          <span key={c.id} className={`check ${c.ok ? 'check-ok' : `check-${c.severity}`}`} title={c.detail}>
            {c.ok ? '✓' : '✕'} {c.id}
          </span>
        ))}
      </div>
    </section>
  )
}

function SignoffPanel({ telemetry, onRun }: { telemetry: Telemetry | null; onRun: () => void }) {
  const [report, setReport] = useState<SignoffReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sec = useElapsed(busy)
  async function run() {
    setBusy(true); setError(null)
    try { setReport(await api.signoff(true)); onRun() }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return (
    <section className="card">
      <div className="signoff-head">
        <h2>Sign-off Ladder</h2>
        <button onClick={run} disabled={busy}>{busy ? 'Running regression…' : 'Run sign-off'}</button>
      </div>
      <p className="muted small">
        lint → design → synthesize → simulate (real 3-way cocotb regression).
        {telemetry?.count ? ` ${telemetry.count} run(s), mean ${telemetry.mean_score}, last ${telemetry.last_score}.` : ''}
      </p>
      {telemetry?.history && telemetry.history.filter((h) => h.score != null).length >= 2 && (
        <div className="trend-row">
          <span className="muted small">score trend</span>
          <Sparkline values={telemetry.history.map((h) => h.score).filter((s): s is number => s != null)} />
        </div>
      )}
      {busy && <Busy label="Sign-off ladder running (includes full cocotb regression)" sec={sec} />}
      {error && <pre className="chat-error">{error}</pre>}
      {report && (
        <>
          <div className={`verdict verdict-${report.verdict}`}>{report.verdict} · {report.grade} ({report.score})</div>
          <div className="ladder">
            {report.stages.map((s) => (
              <div key={s.name} className={`stage stage-${s.status}`}>
                <span className="stage-name">{s.name}</span>
                <span className="stage-status">{s.status}</span>
                <span className="stage-detail muted small">{s.detail}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}

// ---------- Tools tab ----------
function ProgressiveCard() {
  const [r, setR] = useState<Progressive | null>(null)
  const [busy, setBusy] = useState(false)
  const sec = useElapsed(busy)
  async function run() { setBusy(true); try { setR(await api.progressive(true)) } finally { setBusy(false) } }
  return (
    <section className="card">
      <div className="signoff-head">
        <h2>Progressive-coding oracle (#1)</h2>
        <button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run 3-way'}</button>
      </div>
      <p className="muted small">golden (Python) → SystemC → RTL, each proven bit-exact by the scoreboard.</p>
      {busy && <Busy label="Running the cocotb 3-way regression" sec={sec} />}
      {r && (
        <div className="ladder">
          {r.representations.map((rep) => (
            <div key={rep.name} className={`stage stage-${rep.overall === 'pass' ? 'pass' : rep.overall === 'fail' ? 'fail' : 'skip'}`}>
              <span className="stage-name">{rep.name}</span>
              <span className="stage-status">{rep.overall}</span>
              <span className="stage-detail muted small">{rep.role}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function ReflectCard() {
  const [r, setR] = useState<Reflection | null>(null)
  const [busy, setBusy] = useState(false)
  async function run() { setBusy(true); try { setR(await api.reflect()) } finally { setBusy(false) } }
  return (
    <section className="card">
      <div className="signoff-head">
        <h2>Adaptive reflection (#5)</h2>
        <button onClick={run} disabled={busy}>{busy ? '…' : 'Diagnose'}</button>
      </div>
      <p className="muted small">Deterministic error→root-stage tracer over the sign-off ladder.</p>
      {r && (
        <pre className="chat-answer">
{r.ok ? `OK — no failing stage. ${r.skipped?.length ? 'skipped: ' + r.skipped.join(', ') : ''}`
      : `root: ${r.root_stage} (${r.error_source})\n${r.diagnosis}\n→ ${r.action}`}
        </pre>
      )}
    </section>
  )
}

function EquivCard() {
  const [out, setOut] = useState<EquivResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [code, setCode] = useState('')
  async function run() {
    setBusy(true)
    try { setOut(await api.equiv(code)) }
    catch (e) { setOut({ equivalent: false, available: true, status: e instanceof Error ? e.message : 'error', issues: [] }) }
    finally { setBusy(false) }
  }
  return (
    <section className="card">
      <div className="signoff-head">
        <h2>Equivalence / LEC (#7)</h2>
        <button onClick={run} disabled={busy}>{busy ? 'Proving…' : 'Check vs project RTL'}</button>
      </div>
      <p className="muted small">yosys sequential LEC (reduced params). Paste candidate RTL, or leave blank for self-equivalence.</p>
      <textarea value={code} onChange={(e) => setCode(e.target.value)} rows={3} placeholder="candidate Verilog (blank = self-equiv)" />
      {out && (
        <div className={`verdict verdict-${out.equivalent ? 'SIGNED_OFF' : 'REJECTED'}`}>
          {out.status}{out.equivalent ? ' ✓' : ' ✗'}
        </div>
      )}
    </section>
  )
}

function GraphCard() {
  const [node, setNode] = useState('apply_gamma')
  const [out, setOut] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function run() {
    setBusy(true)
    try { const r = await api.graphExplain(node.trim()); setOut(r.available ? (r.result ?? '') : (r.error ?? 'unavailable')) }
    finally { setBusy(false) }
  }
  return (
    <section className="card">
      <div className="signoff-head">
        <h2>Graph RAG (#6)</h2>
        <button onClick={run} disabled={busy || !node.trim()}>{busy ? '…' : 'Explain node'}</button>
      </div>
      <p className="muted small">Knowledge-graph neighborhood (graphify) — grounding for generation/incremental.</p>
      <input className="fld-input" value={node} onChange={(e) => setNode(e.target.value)} placeholder="node name, e.g. apply_gamma" />
      {out && <pre className="chat-answer">{out}</pre>}
    </section>
  )
}

function ToolsTab() {
  return (
    <>
      <ProgressiveCard />
      <ReflectCard />
      <EquivCard />
      <GraphCard />
    </>
  )
}

// ---------- App shell ----------
type Tab = 'verify' | 'plan' | 'tools'

export default function App() {
  const [tab, setTab] = useState<Tab>('verify')
  const [health, setHealth] = useState<Health | null>(null)
  const [data, setData] = useState<VerificationResults | null>(null)
  const [qor, setQor] = useState<QoRReport | null>(null)
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  function refreshTelemetry() { api.telemetry('signoff').then(setTelemetry).catch(() => {}) }

  async function loadAll() {
    setRefreshing(true)
    setError(null)
    await Promise.allSettled([
      api.health().then(setHealth).catch(() => setHealth(null)),
      api.verification().then(setData)
        .catch((e) => setError(e instanceof Error ? e.message : String(e))),
      api.analyze().then(setQor).catch(() => setQor(null)),
      api.telemetry('signoff').then(setTelemetry).catch(() => {}),
    ])
    setUpdatedAt(new Date())
    setRefreshing(false)
  }

  useEffect(() => { loadAll() }, [])

  const tabs: { id: Tab; label: string }[] = [
    { id: 'verify', label: 'Verify' },
    { id: 'plan', label: 'Plan / Ask' },
    { id: 'tools', label: 'Tools' },
  ]

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>AI-Driven RTL Workbench</h1>
          <p className="muted">gamma core · Python golden ↔ SystemC ↔ RTL · plan → generate → verify</p>
        </div>
        <div className="topbar-right">
          <HealthPill health={health} />
          <div className="topbar-actions">
            <button className="btn-ghost" onClick={loadAll} disabled={refreshing}>
              {refreshing ? 'Refreshing…' : '↻ Refresh'}
            </button>
            {updatedAt && (
              <span className="muted small">updated {updatedAt.toLocaleTimeString()}</span>
            )}
          </div>
        </div>
      </header>

      <nav className="tabs">
        {tabs.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? 'tab-active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      {error && <div className="card error-card">Failed to load results: {error}</div>}

      {tab === 'verify' && (data
        ? <VerifyTab data={data} qor={qor} telemetry={telemetry} onSignoff={refreshTelemetry} />
        : <div className="card muted">Loading verification results…</div>)}
      {tab === 'plan' && (
        <>
          <PlanTab gatewayReady={!!health?.has_key} />
          <ChatPanel gatewayReady={!!health?.has_key} />
        </>
      )}
      {tab === 'tools' && <ToolsTab />}
    </div>
  )
}
