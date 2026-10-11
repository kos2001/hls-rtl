import type { NavSelection } from './Navigator'
import type { PatternResult, QoRReport, SkillInfo } from './types'
import { useT } from './i18n'

/**
 * Properties / object inspector — the right-hand pane of an EDA GUI.
 *
 * Whatever is selected in the navigator (or cross-probed from the schematic)
 * is described here as a flat attribute list. Flat on purpose: an inspector
 * that nests is an inspector you have to navigate.
 */

function Row({ k, v, mono = true }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="prop-row">
      <span className="prop-k">{k}</span>
      <span className={`prop-v ${mono ? 'mono' : ''}`}>{v}</span>
    </div>
  )
}

export function Properties({ sel, qor, reference = false }: { sel: NavSelection | null; qor: QoRReport | null; reference?: boolean }) {
  const t = useT()
  return (
    <aside className="properties">
      <div className="nav-title">{t('Properties')}</div>
      {!sel && (
        <p className="muted small prop-empty">
          {t('Select an object in the navigator, or click a cell in the schematic.')}
        </p>
      )}
      {sel && <Body sel={sel} qor={qor} reference={reference} />}
    </aside>
  )
}

function Body({ sel, qor, reference }: { sel: NavSelection; qor: QoRReport | null; reference: boolean }) {
  const t = useT()
  if (sel.kind === 'pattern') {
    const p = sel.data as PatternResult
    return (
      <>
        <div className="prop-head">{p.name}</div>
        <Row k="object" v="test pattern" mono={false} />
        <Row k="status" v={<span className={`badge badge-${reference ? 'expected' : p.status}`}>{reference ? t('Expected') : p.status}</span>} mono={false} />
        <Row k="pixels" v={p.pixels.toLocaleString()} />
        <Row k="mismatches" v={reference ? '—' : p.mismatches} />
        <div className="prop-sep">frame hashes (SHA-256)</div>
        <Row k="golden" v={<span title={p.golden_sha256}>{p.golden_sha256.slice(0, 16)}…</span>} />
        <Row k="rtl" v={reference ? <span className="muted">{t('Not measured')}</span> : <span title={p.rtl_sha256}>{p.rtl_sha256.slice(0, 16)}…</span>} />
        <Row k="systemc" v={reference ? <span className="muted">{t('Not measured')}</span> : p.sc_sha256
          ? <span title={p.sc_sha256}>{p.sc_sha256.slice(0, 16)}…</span>
          : <span className="muted">skipped — no build/sc_out.txt</span>} />
        <p className="prop-note muted small">
          {reference ? t('These are expected outputs, not measured RTL results. Run sign-off to verify the implementation.') : t('A skipped stage is missing evidence, never a pass. 2-state simulation does not cover X/Z behavior.')}
        </p>
      </>
    )
  }

  if (sel.kind === 'port') {
    return (
      <>
        <div className="prop-head">{sel.id}</div>
        <Row k="object" v="port" mono={false} />
        <Row k="declaration" v={String(sel.data)} />
        <Row k="module" v="gamma" />
        <p className="prop-note muted small">
          Handshake contract: <code>in_ready = (count != FIFO_DEPTH)</code>, registered
          occupancy only — there is no combinational <code>out_ready → in_ready</code> path.
        </p>
      </>
    )
  }

  if (sel.kind === 'representation') {
    return (
      <>
        <div className="prop-head">{sel.id}</div>
        <Row k="object" v="model representation" mono={false} />
        <Row k="role" v={String(sel.data)} mono={false} />
        <p className="prop-note muted small">
          The Python golden defines the expected hashes; SystemC and RTL are candidates
          proven against it. If RTL and golden disagree, the RTL is wrong until shown otherwise.
        </p>
      </>
    )
  }

  if (sel.kind === 'skill') {
    const s = sel.data as SkillInfo
    return (
      <>
        <div className="prop-head">{s.name}</div>
        <Row k="object" v="agent skill" mono={false} />
        <Row k="category" v={s.category} />
        <Row k="state" v={
          <span className={`badge badge-${s.installed ? 'pass' : 'skip'}`}>
            {s.installed ? 'loaded' : s.source}
          </span>} mono={false} />
        <Row k="purpose" v={s.purpose} mono={false} />
        {s.description && <p className="prop-note muted small">{s.description}</p>}
        {!s.installed && (
          <p className="prop-note prop-warn small">
            Not installed in the serving profile — the agent cannot load it.
            Run <code>python scripts/sync_hermes_skills.py</code>, then restart the gateway.
          </p>
        )}
      </>
    )
  }

  if (sel.kind === 'flow') {
    return (
      <>
        <div className="prop-head">{sel.id}</div>
        <Row k="object" v="schematic cell" mono={false} />
        {Object.entries((sel.data ?? {}) as Record<string, unknown>)
          .filter(([, v]) => v !== null && v !== undefined && v !== '')
          .map(([k, v]) => <Row key={k} k={k} v={String(v)} />)}
      </>
    )
  }

  // design
  const m = qor?.metrics
  return (
    <>
      <div className="prop-head">gamma</div>
      <Row k="object" v="module (top)" mono={false} />
      <Row k="source" v="rtl/gamma.v" />
      <Row k="dialect" v={m?.hdl_dialect ?? 'verilog-2001'} />
      <Row k="reset" v={m ? `${m.reset_kind} / ${m.reset_active}` : 'async / active-low'} />
      <Row k="latency" v="1 cycle (accepted → valid)" mono={false} />
      <Row k="fifo depth" v="8 (parameterizable)" mono={false} />
      {qor && <>
        <div className="prop-sep">synthesis (yosys)</div>
        <Row k="flops" v={String(m?.synth_flops ?? '—')} />
        <Row k="cells" v={String(m?.synth_cells ?? '—')} />
        <Row k="latches" v={String(m?.synth_latches ?? '—')} />
        <Row k="score" v={`${qor.score}/100 (${qor.grade})`} />
      </>}
      <p className="prop-note muted small">
        Verilog-2001 on purpose — the cocotb flow runs <code>TOPLEVEL_LANG=verilog</code>
        and the QoR analyzer does not penalize <code>reg</code>/<code>wire</code>.
      </p>
    </>
  )
}
