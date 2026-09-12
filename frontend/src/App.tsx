import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from './api'
import { Console } from './Console'
import { HelpPane } from './Help'
import { KnowledgePane } from './Knowledge'
import { Navigator } from './Navigator'
import { Overview } from './Overview'
import type { NavSelection } from './Navigator'
import { Properties } from './Properties'
import { SchematicPane } from './Schematic'
import { Splitter, applySavedPanes, resetPanes } from './Splitter'
import { WaveformPane } from './Waveform'
import { ChatPanel, PlanTab } from './PlanAsk'
import { log, traced } from './log'
import { Sparkline } from './ui'
import type {
  EquivResult, Health, PatternResult, Progressive, QoRReport, Reflection,
  KbStats, SchematicNode, SignoffReport, SkillReport, Telemetry, VerificationResults,
} from './types'

/**
 * Workbench shell laid out like a commercial EDA tool (Cadence / Synopsys):
 * menu bar, run toolbar, design navigator (left), tabbed work area (centre),
 * properties inspector (right), tool transcript (bottom), status bar.
 *
 * The layout is the point, not decoration: every flow the backend exposes writes
 * severity-tagged messages into one transcript, so the console is a complete,
 * greppable record of the session — the way an engineer actually debugs a run.
 */

type View = 'overview' | 'scoreboard' | 'waveform' | 'schematic' | 'quality' | 'signoff'
  | 'flows' | 'knowledge' | 'assistant' | 'help'

const VIEWS: { id: View; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'scoreboard', label: 'Scoreboard' },
  { id: 'waveform', label: 'Waveform' },
  { id: 'schematic', label: 'Schematic' },
  { id: 'quality', label: 'Quality' },
  { id: 'signoff', label: 'Sign-off' },
  { id: 'flows', label: 'Flows' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'assistant', label: 'Assistant' },
  { id: 'help', label: 'Manual' },
]

// ---------------- shared bits ----------------
function Sha({ value }: { value: string | null }) {
  if (!value) return <span className="sha sha-none">— skipped</span>
  return <span className="sha" title={value}>{value.slice(0, 12)}…</span>
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === 'pass' ? 'pass' : status === 'fail' ? 'fail' : 'skip'
  return <span className={`badge badge-${cls}`}>{status}</span>
}

// ---------------- menu bar ----------------
function Menu({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])
  return (
    <div className="menu" ref={ref}>
      <button className={`menu-btn ${open ? 'menu-btn-open' : ''}`} onClick={() => setOpen(!open)}>
        {label}
      </button>
      {open && <div className="menu-pop" onClick={() => setOpen(false)}>{children}</div>}
    </div>
  )
}

function MenuItem({ onClick, children, accel, disabled }:
  { onClick: () => void; children: React.ReactNode; accel?: string; disabled?: boolean }) {
  return (
    <button className="menu-item" onClick={onClick} disabled={disabled}>
      <span>{children}</span>
      {accel && <span className="menu-accel">{accel}</span>}
    </button>
  )
}

// ---------------- scoreboard ----------------
function Scoreboard({ data, onPick }:
  { data: VerificationResults; onPick: (p: PatternResult) => void }) {
  const allPass = data.summary.failed === 0
  return (
    <div className="view-scroll">
      <div className="stat-strip">
        <div className={`stat ${allPass ? 'stat-ok' : 'stat-fail'}`}>
          <div className="stat-value">{allPass ? 'PASS' : 'FAIL'}</div>
          <div className="stat-label">scoreboard verdict</div>
        </div>
        <div className="stat">
          <div className="stat-value">{data.summary.passed}/{data.summary.total_patterns}</div>
          <div className="stat-label">patterns bit-exact</div>
        </div>
        <div className="stat">
          <div className="stat-value">{data.summary.total_pixels.toLocaleString()}</div>
          <div className="stat-label">pixels compared</div>
        </div>
        <div className="stat">
          <div className="stat-value">{data.design.pixel_w}b / {data.design.lut_depth}</div>
          <div className="stat-label">pixel width / LUT depth</div>
        </div>
        <div className="stat">
          <div className="stat-value">{Object.values(data.gammas).join(' · ')}</div>
          <div className="stat-label">γ per channel (R·G·B)</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><h2>Pattern Comparison Matrix</h2></div>
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>pattern</th><th className="num">pixels</th><th>status</th>
                <th className="num">mism.</th><th>golden sha-256</th>
                <th>rtl sha-256</th><th>systemc sha-256</th>
              </tr>
            </thead>
            <tbody>
              {data.patterns.map((p) => (
                <tr key={p.name} onClick={() => onPick(p)} className="row-pick">
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
        <p className="panel-foot muted small">{data.source}</p>
      </div>

      <div className="panel panel-caveat">
        <strong>Coverage caveat.</strong> The regression runs under Verilator, which is
        2-state. These hashes prove value equality on the listed patterns; they do not
        cover X-propagation or reset-initialization behaviour. Cross-check with Icarus
        (<code>make -C tb SIM=icarus</code>) before claiming those are clean.
      </div>
    </div>
  )
}

// ---------------- quality ----------------
function Quality({ qor }: { qor: QoRReport | null }) {
  if (!qor) return <div className="pane-empty muted">No QoR report — reload from the toolbar.</div>
  const m = qor.metrics
  const errs = qor.checks.filter((c) => !c.ok && c.severity === 'error')
  const warns = qor.checks.filter((c) => !c.ok && c.severity === 'warn')
  return (
    <div className="view-scroll">
      <div className="panel">
        <div className="panel-head"><h2>Design Quality (QoR)</h2></div>
        <div className="qor-head">
          <div className={`grade grade-${qor.grade}`}>{qor.grade}</div>
          <div>
            <div className="stat-value">{qor.score}<span className="muted">/100</span></div>
            <div className="muted small">
              lint: {qor.lint_tool} · {m.hdl_dialect} · {m.reset_kind}/{m.reset_active} reset
            </div>
          </div>
          <div className="qor-metrics">
            <span className="pill pill-muted">flops {m.synth_flops ?? '—'}</span>
            <span className="pill pill-muted">cells {m.synth_cells ?? '—'}</span>
            <span className={`pill ${m.synth_latches ? 'pill-fail' : 'pill-ok'}`}>
              latches {m.synth_latches ?? '—'}
            </span>
            <span className={`pill ${m.synthesizable ? 'pill-ok' : 'pill-warn'}`}>
              {m.synthesizable ? 'synthesizes' : 'unsynth'}
            </span>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Design Rule Checks</h2>
          <span className="muted small">
            {errs.length} error · {warns.length} warning · {qor.checks.length} total
          </span>
        </div>
        <div className="table-wrap">
          <table className="grid">
            <thead><tr><th>severity</th><th>rule</th><th>result</th><th>detail</th></tr></thead>
            <tbody>
              {qor.checks.map((c) => (
                <tr key={c.id}>
                  <td><span className={`sev-tag sev-tag-${c.ok ? 'ok' : c.severity}`}>
                    {c.ok ? 'PASS' : c.severity.toUpperCase()}</span></td>
                  <td className="mono">{c.id}</td>
                  <td>{c.ok ? '✓' : '✕'}</td>
                  <td className="muted small">{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---------------- sign-off ----------------
function SignoffView({ report, telemetry, busy, onRun }: {
  report: SignoffReport | null; telemetry: Telemetry | null
  busy: boolean; onRun: () => void
}) {
  const hist = (telemetry?.history ?? []).map((h) => h.score).filter((s): s is number => s != null)
  return (
    <div className="view-scroll">
      <div className="panel">
        <div className="panel-head">
          <h2>Sign-off Ladder</h2>
          <button className="btn-run" onClick={onRun} disabled={busy}>
            {busy ? '■ Running…' : '▶ Run sign-off'}
          </button>
        </div>
        <p className="muted small">
          lint → design → synthesize → simulate. The simulate stage runs the real
          3-way cocotb regression, not a mock.
          {telemetry?.count ? ` ${telemetry.count} run(s) archived, mean ${telemetry.mean_score}.` : ''}
        </p>
        {hist.length >= 2 && (
          <div className="trend-row">
            <span className="muted small">score trend</span><Sparkline values={hist} />
          </div>
        )}
        {report && (
          <>
            <div className={`verdict verdict-${report.verdict}`}>
              VERDICT: {report.verdict} · {report.grade} ({report.score}/100)
            </div>
            <div className="table-wrap">
              <table className="grid">
                <thead><tr><th>stage</th><th>status</th><th>gating</th><th>detail</th></tr></thead>
                <tbody>
                  {report.stages.map((s) => (
                    <tr key={s.name}>
                      <td className="mono">{s.name}</td>
                      <td><StatusBadge status={s.status} /></td>
                      <td className="muted">{s.gating ? 'yes' : 'no'}</td>
                      <td className="muted small">{s.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {!report && !busy && (
          <p className="muted small">No sign-off run in this session. Results archive to <code>runs/</code>.</p>
        )}
      </div>
    </div>
  )
}

// ---------------- flows ----------------
function Flows() {
  const [prog, setProg] = useState<Progressive | null>(null)
  const [refl, setRefl] = useState<Reflection | null>(null)
  const [equiv, setEquiv] = useState<EquivResult | null>(null)
  const [code, setCode] = useState('')
  const [node, setNode] = useState('apply_gamma')
  const [graph, setGraph] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  async function runProgressive() {
    setBusy('prog')
    const r = await traced(
      { stage: 'progressive', tool: 'cocotb 3-way', design: 'gamma', cmd: 'make -C tb' },
      () => api.progressive(true),
      (v) => {
        for (const rep of v.representations) {
          const sev = rep.overall === 'pass' ? log.info : rep.overall === 'skip' ? log.warn : log.error
          sev('EQUIV', `${rep.name} (${rep.role}): ${rep.overall}`)
        }
        return { status: v.bit_exact ? 'pass' : 'fail',
                 extra: `${v.patterns_total} patterns` }
      })
    if (r) setProg(r)
    setBusy(null)
  }

  async function runReflect() {
    setBusy('refl')
    const r = await traced(
      { stage: 'reflect', tool: 'reflection', design: 'gamma', cmd: 'reflect --from-analyzer' },
      () => api.reflect(),
      (v) => {
        if (v.ok) log.info('REFLECT', 'no failing stage')
        else log.error('REFLECT', `root stage ${v.root_stage} (${v.error_source}): ${v.diagnosis}`)
        return { status: v.ok ? 'pass' : 'fail' }
      })
    if (r) setRefl(r)
    setBusy(null)
  }

  async function runEquiv() {
    setBusy('equiv')
    const r = await traced(
      { stage: 'lec', tool: 'yosys equiv_induct', design: 'gamma',
        cmd: `equiv ${code.trim() ? 'candidate' : 'self'} vs rtl/gamma.v` },
      () => api.equiv(code),
      (v) => {
        (v.equivalent ? log.info : log.error)('LEC', `${v.status}`)
        for (const i of v.issues) log.warn('LEC', i)
        return { status: v.equivalent ? 'pass' : 'fail' }
      })
    if (r) setEquiv(r)
    setBusy(null)
  }

  async function runGraph() {
    setBusy('graph')
    const r = await traced(
      { stage: 'graph-rag', tool: 'graphify', design: 'repo', cmd: `graph explain ${node}` },
      () => api.graphExplain(node.trim()),
      (v) => {
        if (!v.available) log.warn('GRAPH', v.error ?? 'graph unavailable')
        return { status: v.available ? 'pass' : 'skip' }
      })
    if (r) setGraph(r.available ? (r.result ?? '') : (r.error ?? 'unavailable'))
    setBusy(null)
  }

  return (
    <div className="view-scroll flows-grid">
      <div className="panel">
        <div className="panel-head">
          <h2>Progressive-coding oracle</h2>
          <button className="btn-run" onClick={runProgressive} disabled={!!busy}>
            {busy === 'prog' ? '■ Running…' : '▶ Run 3-way'}
          </button>
        </div>
        <p className="muted small">golden (Python) → SystemC → RTL, each proven bit-exact by the scoreboard.</p>
        {prog && (
          <table className="grid">
            <thead><tr><th>representation</th><th>role</th><th>verdict</th></tr></thead>
            <tbody>
              {prog.representations.map((r) => (
                <tr key={r.name}>
                  <td className="mono">{r.name}</td>
                  <td className="muted small">{r.role}</td>
                  <td><StatusBadge status={r.overall} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Adaptive reflection</h2>
          <button className="btn-run" onClick={runReflect} disabled={!!busy}>
            {busy === 'refl' ? '■ …' : '▶ Diagnose'}
          </button>
        </div>
        <p className="muted small">Deterministic error → root-stage tracer over the sign-off ladder.</p>
        {refl && (
          <pre className="out-block">
{refl.ok
  ? `OK — no failing stage.${refl.skipped?.length ? `\nskipped: ${refl.skipped.join(', ')}` : ''}`
  : `root   : ${refl.root_stage} (${refl.error_source})\ncause  : ${refl.diagnosis}\naction : ${refl.action}`}
          </pre>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Logical equivalence (LEC)</h2>
          <button className="btn-run" onClick={runEquiv} disabled={!!busy}>
            {busy === 'equiv' ? '■ Proving…' : '▶ Check'}
          </button>
        </div>
        <p className="muted small">
          yosys sequential LEC at reduced params. Blank = self-equivalence sanity check.
        </p>
        <textarea value={code} onChange={(e) => setCode(e.target.value)} rows={3}
                  placeholder="candidate Verilog (blank = self-equiv)" />
        {equiv && (
          <div className={`verdict verdict-${equiv.equivalent ? 'SIGNED_OFF' : 'REJECTED'}`}>
            {equiv.status} {equiv.equivalent ? '✓' : '✗'}
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Graph RAG</h2>
          <button className="btn-run" onClick={runGraph} disabled={!!busy || !node.trim()}>
            {busy === 'graph' ? '■ …' : '▶ Explain'}
          </button>
        </div>
        <p className="muted small">Knowledge-graph neighborhood (graphify) — grounding context.</p>
        <input className="fld-input" value={node} onChange={(e) => setNode(e.target.value)}
               placeholder="node name, e.g. apply_gamma" />
        {graph && <pre className="out-block">{graph}</pre>}
      </div>
    </div>
  )
}

// ---------------- app ----------------
export default function App() {
  const [view, setView] = useState<View>('overview')
  const [health, setHealth] = useState<Health | null>(null)
  const [data, setData] = useState<VerificationResults | null>(null)
  const [qor, setQor] = useState<QoRReport | null>(null)
  const [skills, setSkills] = useState<SkillReport | null>(null)
  const [kb, setKb] = useState<KbStats | null>(null)
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null)
  const [signoff, setSignoff] = useState<SignoffReport | null>(null)
  const [sel, setSel] = useState<NavSelection | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [consoleOpen, setConsoleOpen] = useState(true)
  const [showNav, setShowNav] = useState(true)
  const [showProps, setShowProps] = useState(true)
  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => (localStorage.getItem('wb-theme') as 'dark' | 'light') || 'dark')
  const shellRef = useRef<HTMLDivElement>(null)

  // Restore dragged pane sizes before the first paint, so a rebalanced
  // workspace does not visibly snap from the fluid default to the saved one.
  useLayoutEffect(() => { applySavedPanes(shellRef.current) }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('wb-theme', theme)
  }, [theme])

  const loadAll = useCallback(async () => {
    setBusy('load')
    log.cmd('reload --all')
    await Promise.allSettled([
      api.health().then(setHealth).catch(() => {
        setHealth(null); log.error('CONN', 'api-server unreachable on /api/health')
      }),
      traced({ stage: 'scoreboard', tool: 'golden-model', design: 'gamma',
               cmd: 'read_results --live' },
        () => api.verification(),
        (v) => {
          const f = v.summary.failed
          if (f) log.error('SCOREBOARD', `${f} of ${v.summary.total_patterns} patterns mismatched`)
          else log.info('SCOREBOARD', `${v.summary.passed}/${v.summary.total_patterns} patterns bit-exact (${v.summary.total_pixels.toLocaleString()} px)`)
          return { status: f ? 'fail' : 'pass' }
        }).then((v) => v && setData(v)),
      traced({ stage: 'analyze', tool: 'verilator+yosys', design: 'gamma',
               cmd: 'analyze rtl/gamma.v' },
        () => api.analyze(),
        (v) => {
          for (const c of v.checks) {
            if (c.ok) continue
            const f = c.severity === 'error' ? log.error : c.severity === 'warn' ? log.warn : log.note
            f(c.id.toUpperCase().slice(0, 10), `gamma: ${c.detail}`)
          }
          log.info('SYNTH', `gamma: ${v.metrics.synth_cells ?? '?'} cells, ${v.metrics.synth_flops ?? '?'} flops, ${v.metrics.synth_latches ?? 0} latches`)
          return { status: v.score >= 70 ? 'pass' : 'fail', extra: `score ${v.score}/100 (${v.grade})` }
        }).then((v) => v && setQor(v)),
      api.skills().then((s) => {
        setSkills(s)
        log.info('SKILLS', `profile ${s.profile}: ${s.active.length}/${s.skills.length} loaded`)
        for (const m of s.missing) log.warn('SKILLS', `${m}: not installed in the serving profile — agent cannot load it`)
      }).catch(() => setSkills(null)),
      api.telemetry('signoff').then(setTelemetry).catch(() => {}),
      api.kbStats().then((k) => {
        setKb(k)
        log.info('KB', `${k.chunks} passages indexed (${k.pinned} pinned), ${k.terms} terms`)
      }).catch(() => setKb(null)),
    ])
    setUpdatedAt(new Date())
    setBusy(null)
  }, [])

  useEffect(() => { void loadAll() }, [loadAll])

  async function runSignoff() {
    setBusy('signoff')
    setView('signoff')
    const r = await traced(
      { stage: 'signoff', tool: 'lint+yosys+cocotb', design: 'gamma', cmd: 'signoff --run-regression' },
      () => api.signoff(true),
      (v) => {
        for (const s of v.stages) {
          const f = s.status === 'pass' ? log.info : s.status === 'skip' ? log.warn : log.error
          f('STAGE', `${s.name}: ${s.status}${s.gating ? ' (gating)' : ''} — ${s.detail}`)
        }
        return { status: v.verdict, extra: `score ${v.score}/100 (${v.grade})` }
      })
    if (r) setSignoff(r)
    api.telemetry('signoff').then(setTelemetry).catch(() => {})
    setBusy(null)
  }

  function exportTranscript() {
    const el = document.querySelector('.console-body')
    const text = el?.textContent ?? ''
    const blob = new Blob([text], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `gamma-transcript-${new Date().toISOString().slice(0, 19).replace(/:/g, '')}.log`
    a.click()
    URL.revokeObjectURL(a.href)
    log.info('CONSOLE', `transcript exported as ${a.download}`)
  }

  const gatewayReady = !!health?.has_key

  return (
    <div className="workbench" ref={shellRef}>
      {/* ---- menu bar ---- */}
      <div className="menubar">
        <div className="brand">
          <span className="brand-mark">RTL</span>
          <span className="brand-name">Verification Workbench</span>
          <span className="brand-design">gamma</span>
          <span className="brand-thesis">golden model as executable oracle · 3-way bit-exact</span>
        </div>
        <Menu label="File">
          <MenuItem onClick={loadAll} accel="⌘R">Reload all</MenuItem>
          <MenuItem onClick={exportTranscript}>Export transcript…</MenuItem>
          <MenuItem onClick={() => {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
            const a = document.createElement('a')
            a.href = URL.createObjectURL(blob); a.download = 'results.json'; a.click()
            URL.revokeObjectURL(a.href)
          }} disabled={!data}>Export results.json…</MenuItem>
        </Menu>
        <Menu label="View">
          <MenuItem onClick={() => setShowNav((v) => !v)}>{showNav ? '✓ ' : ''}Design navigator</MenuItem>
          <MenuItem onClick={() => setShowProps((v) => !v)}>{showProps ? '✓ ' : ''}Properties</MenuItem>
          <MenuItem onClick={() => setConsoleOpen((v) => !v)}>{consoleOpen ? '✓ ' : ''}Transcript</MenuItem>
          <MenuItem onClick={() => {
            resetPanes(shellRef.current)
            setShowNav(true); setShowProps(true); setConsoleOpen(true)
            log.info('LAYOUT', 'pane sizes reset to the fluid defaults')
          }}>Reset layout</MenuItem>
          <MenuItem onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? 'Light' : 'Dark'} theme
          </MenuItem>
        </Menu>
        <Menu label="Run">
          <MenuItem onClick={runSignoff} disabled={!!busy}>Sign-off ladder</MenuItem>
          <MenuItem onClick={() => setView('waveform')}>Traced simulation…</MenuItem>
          <MenuItem onClick={() => setView('schematic')}>Elaborate schematic</MenuItem>
          <MenuItem onClick={() => setView('flows')}>Flows (LEC, reflection)…</MenuItem>
          <MenuItem onClick={() => setView('knowledge')}>Knowledge retrieval…</MenuItem>
        </Menu>
        <Menu label="Help">
          <MenuItem onClick={() => setView('help')} accel="?">User manual</MenuItem>
          <MenuItem onClick={() => setView('overview')}>What is this?</MenuItem>
          <MenuItem onClick={() => {
            log.info('ABOUT', 'gamma verification workbench — golden(Python) / SystemC / RTL 3-way bit-exact scoreboard')
            log.note('ABOUT', 'open-source flow: verilator, icarus, cocotb, yosys, sby')
            setConsoleOpen(true)
          }}>About</MenuItem>
        </Menu>

        <div className="menubar-right">
          <span className={`conn ${health ? 'conn-ok' : 'conn-bad'}`}>
            {health ? 'connected' : 'offline'}
          </span>
        </div>
      </div>

      {/* ---- toolbar ---- */}
      <div className="toolbar">
        <button className="tool" onClick={loadAll} disabled={!!busy} title="Reload all data">
          <span className="tool-ico">↻</span>Reload
        </button>
        <span className="tool-sep" />
        <button className="tool" onClick={() => setView('waveform')} title="Waveform viewer">
          <span className="tool-ico">◠</span>Waveform
        </button>
        <button className="tool" onClick={() => setView('schematic')} title="RTL schematic">
          <span className="tool-ico">▦</span>Schematic
        </button>
        <span className="tool-sep" />
        <button className="tool tool-primary" onClick={runSignoff} disabled={!!busy}>
          <span className="tool-ico">▶</span>{busy === 'signoff' ? 'Running sign-off…' : 'Run sign-off'}
        </button>
        <div className="toolbar-right">
          {skills && (
            <span className={`pill ${skills.missing.length ? 'pill-warn' : 'pill-ok'}`}
                  title={skills.missing.length ? `missing: ${skills.missing.join(', ')}` : 'all skills loaded'}>
              skills {skills.active.length}/{skills.skills.length}
            </span>
          )}
          <span className={`pill ${health?.verilator ? 'pill-ok' : 'pill-warn'}`}>
            verilator {health?.verilator ? 'ok' : 'missing'}
          </span>
          <span className={`pill ${gatewayReady ? 'pill-ok' : 'pill-warn'}`}>
            hermes {gatewayReady ? 'ready' : 'no key'}
          </span>
        </div>
      </div>

      {/* ---- workspace ---- */}
      <div className="workspace">
        {showNav && (
          <>
            <Navigator data={data} skills={skills} selected={sel} onSelect={setSel} />
            <Splitter axis="x" varName="--nav-w" min={150} max={520} label="Navigator width" />
          </>
        )}

        <main className="work-area">
          <div className="view-tabs">
            {VIEWS.map((v) => (
              <button key={v.id}
                      className={`view-tab ${view === v.id ? 'view-tab-active' : ''}`}
                      onClick={() => setView(v.id)}>
                {v.label}
              </button>
            ))}
          </div>

          <div className="view-body">
            {view === 'overview' && (
              <Overview data={data} qor={qor} skills={skills} kb={kb}
                        onGo={(v) => setView(v as View)} />
            )}
            {view === 'scoreboard' && (data
              ? <Scoreboard data={data} onPick={(p) => setSel({ kind: 'pattern', id: p.name, data: p })} />
              : <div className="pane-empty muted">Loading verification results…</div>)}
            {view === 'waveform' && <WaveformPane />}
            {view === 'schematic' && (
              <SchematicPane onSelect={(n: SchematicNode) => setSel({
                kind: 'flow',
                id: n.name || n.label,
                data: {
                  label: n.label, type: n.type, class: n.cls, level: n.layer,
                  width: `${n.width} bit`,
                  source: n.src_line ? `rtl/gamma.v:${n.src_line}` : '',
                  sequential: n.seq ? 'yes' : 'no',
                },
              })} />
            )}
            {view === 'quality' && <Quality qor={qor} />}
            {view === 'signoff' && (
              <SignoffView report={signoff} telemetry={telemetry}
                           busy={busy === 'signoff'} onRun={runSignoff} />
            )}
            {view === 'flows' && <Flows />}
            {view === 'knowledge' && <KnowledgePane />}
            {view === 'help' && <HelpPane />}
            {view === 'assistant' && (
              <div className="view-scroll">
                <PlanTab gatewayReady={gatewayReady} />
                <ChatPanel gatewayReady={gatewayReady} skills={skills} />
              </div>
            )}
          </div>
        </main>

        {showProps && (
          <>
            <Splitter axis="x" varName="--props-w" min={170} max={560} invert
                      label="Properties width" />
            <Properties sel={sel} qor={qor} />
          </>
        )}
      </div>

      {/* ---- transcript ---- */}
      {consoleOpen && (
        <Splitter axis="y" varName="--console-h" min={80} max={700} invert
                  label="Transcript height" />
      )}
      <Console open={consoleOpen} onToggle={() => setConsoleOpen((v) => !v)} />

      {/* ---- status bar ---- */}
      <div className="statusbar">
        <span className="sb-item">design: <b>{data?.design.module ?? 'gamma'}</b></span>
        <span className="sb-item">
          scoreboard: <b className={data?.summary.failed ? 'sb-fail' : 'sb-ok'}>
            {data ? `${data.summary.passed}/${data.summary.total_patterns}` : '—'}
          </b>
        </span>
        <span className="sb-item">QoR: <b>{qor ? `${qor.score} (${qor.grade})` : '—'}</b></span>
        <span className="sb-item">profile: <b>{skills?.profile ?? '—'}</b></span>
        <span className="sb-item">kb: <b>{kb ? `${kb.chunks} psg` : '—'}</b></span>
        <span className="sb-item">model: <b>{health?.model ?? '—'}</b></span>
        <span className="sb-spacer" />
        {busy && <span className="sb-item sb-busy"><i className="spinner" />{busy}…</span>}
        <span className="sb-item muted">{updatedAt ? `updated ${updatedAt.toLocaleTimeString()}` : 'loading…'}</span>
      </div>
    </div>
  )
}
