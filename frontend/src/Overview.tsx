import { useState } from 'react'
import { Icon, type IconName } from './components/Icon'
import { useT } from './i18n'
import { isReference } from './evidence'
import type { View } from './navigation'
import type { KbStats, PatternResult, QoRReport, SkillReport, Telemetry, VerificationResults } from './types'
import { StatusBadge } from './views/shared'

interface Props {
  data: VerificationResults | null
  qor: QoRReport | null
  skills: SkillReport | null
  kb: KbStats | null
  telemetry: Telemetry | null
  busy: boolean
  onGo: (view: View) => void
  onPick: (pattern: PatternResult) => void
  onRun: () => void
  onReload: () => void
}

function Metric({ label, value, suffix, detail, icon, tone }: { label: string; value: string; suffix?: string; detail: string; icon: IconName; tone?: string }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><Icon name={icon} size={17} /></div><div className={`metric-value ${tone ?? ''}`}>{value}<span>{suffix}</span></div><div className="metric-detail">{detail}</div></div>
}

function roundEven(value: number) {
  const lower = Math.floor(value)
  return value - lower === 0.5 ? (lower % 2 ? lower + 1 : lower) : Math.round(value)
}

/** Reference LUT curves from the golden-model equation, not measured waveforms. */
function GammaChart({ data }: { data: VerificationResults | null }) {
  const t = useT()
  const [input, setInput] = useState(128)
  const colors = ['var(--curve-r)', 'var(--curve-g)', 'var(--curve-b)']
  const channels = data ? Object.entries(data.gammas) : []
  const maxIn = (data?.design.lut_depth ?? 256) - 1
  const maxOut = 2 ** (data?.design.pixel_w ?? 8) - 1
  const selected = Math.min(input, maxIn)
  const output = (x: number, gamma: number) => roundEven((x / maxIn) ** (1 / gamma) * maxOut)
  const x = (value: number) => 45 + value / maxIn * 500
  const y = (value: number) => 192 - value / maxOut * 165
  return <>
    <div className="chart-heading"><div><h2>{t('Gamma transfer curves')}</h2><p>{t('Independent channels. One reference model.')}</p></div><span className="subtle-tag">{t('REFERENCE LUT')}</span></div>
    {data ? <><div className="chart-legend">{channels.map(([channel, gamma], index) => <span key={channel}><i style={{ background: colors[index % colors.length] }} />{channel.toUpperCase()}<span className="mono">γ {gamma}</span></span>)}</div>
      <svg className="gamma-chart" viewBox="0 0 580 225" role="img" aria-label={t('Gamma correction reference curves for red, green, and blue channels')}
        onMouseMove={event => { const bounds = event.currentTarget.getBoundingClientRect(); setInput(Math.max(0, Math.min(maxIn, Math.round(((event.clientX - bounds.left) / bounds.width * 580 - 45) / 500 * maxIn)))) }}>
        {[0, 0.25, 0.5, 0.75, 1].map(fraction => <g key={fraction}><line x1="45" x2="545" y1={y(fraction * maxOut)} y2={y(fraction * maxOut)} className="chart-grid" /><text x="32" y={y(fraction * maxOut) + 4} textAnchor="end">{Math.round(fraction * maxOut)}</text><line x1={x(fraction * maxIn)} x2={x(fraction * maxIn)} y1="27" y2="192" className="chart-grid chart-grid-vertical" /><text x={x(fraction * maxIn)} y="213" textAnchor="middle">{Math.round(fraction * maxIn)}</text></g>)}
        <line x1="45" x2="545" y1="192" y2="27" className="chart-linear" />
        {channels.map(([channel, gamma], index) => <path key={channel} d={Array.from({ length: 129 }, (_, i) => { const value = Math.round(i / 128 * maxIn); return `${i ? 'L' : 'M'}${x(value).toFixed(2)},${y(output(value, gamma)).toFixed(2)}` }).join(' ')} fill="none" stroke={colors[index % colors.length]} strokeWidth="2.5" />)}
        <line x1={x(selected)} x2={x(selected)} y1="27" y2="192" className="chart-marker" />
        {channels.map(([channel, gamma], index) => <circle key={channel} cx={x(selected)} cy={y(output(selected, gamma))} r="4" fill={colors[index % colors.length]} stroke="var(--panel)" strokeWidth="2" />)}
      </svg>
      <div className="chart-controls"><label htmlFor="gamma-input">{t('Input')} <b className="mono">{selected}</b></label><input id="gamma-input" type="range" min="0" max={maxIn} value={selected} onChange={event => setInput(Number(event.target.value))} />
        <div className="chart-output">{channels.map(([channel, gamma], index) => <span key={channel} style={{ color: colors[index % colors.length] }}>{channel.toUpperCase()} <b>{output(selected, gamma)}</b></span>)}</div></div>
      <p className="chart-caption">{t('Reference equation: output = round((input / max)^(1/γ) × max).')}</p>
    </> : <div className="chart-no-data"><Icon name="chart" size={30} /><span>{t('Load verification results to explore the reference curves.')}</span></div>}
  </>
}

export function Overview({ data, qor, skills, kb, telemetry, busy, onGo, onPick, onRun, onReload }: Props) {
  const t = useT()
  const reference = isReference(data)
  const snapshot = data?.resultMode === 'snapshot'
  const total = data?.summary.total_patterns ?? 0
  const allPass = total > 0 && data?.summary.failed === 0 && data.summary.passed === total
  const hasSc = !reference && !!data?.patterns.length && data.patterns.every(pattern => !!pattern.sc_sha256)
  const scMatches = hasSc && data!.patterns.every(pattern => pattern.sc_sha256 === pattern.golden_sha256)
  const rtlMatches = !reference && !!data?.patterns.length && data.patterns.every(pattern => pattern.rtl_sha256 === pattern.golden_sha256 && pattern.status === 'pass')
  const passRate = total ? Math.round((data!.summary.passed / total) * 100) : 0
  const models = [
    { title: 'Python golden', language: 'Python · NumPy', icon: 'book' as const, status: data ? 'oracle' : 'skip', detail: t('Independent executable reference') },
    { title: 'SystemC', language: 'C++ · cycle-accurate', icon: 'flow' as const, status: hasSc ? scMatches ? 'pass' : 'fail' : 'skip', detail: hasSc ? t('Frame hashes compared to golden') : t('Missing comparison evidence') },
    { title: 'Verilog RTL', language: 'Verilog-2001', icon: 'chip' as const, status: data && !reference ? rtlMatches ? 'pass' : 'fail' : 'skip', detail: data && !reference ? `${data.summary.passed}/${total} ${t('patterns bit-exact')}` : reference ? t('Measured simulation required') : t('no results loaded') },
  ]
  const actions: { title: string; detail: string; icon: IconName; view: View }[] = [
    { title: 'Inspect waveforms', detail: 'Understand signal timing', icon: 'wave', view: 'waveform' },
    { title: 'Explore schematic', detail: 'Follow your design connections', icon: 'chip', view: 'schematic' },
    { title: 'Ask the assistant', detail: 'Answers grounded in your project', icon: 'sparkles', view: 'assistant' },
  ]

  return <div className="view-scroll overview-dashboard">
    {snapshot && <div className="snapshot-notice" role="status"><Icon name="info" size={18} /><span><strong>{t('You are viewing a saved snapshot.')}</strong> {t('Live verification and tool status will return when the backend reconnects.')}</span><button disabled={busy} onClick={onReload}>{t('Reconnect')}<Icon name="refresh" size={14} /></button></div>}
    <section className={`verification-banner ${reference ? 'banner-reference' : allPass ? 'banner-pass' : data ? 'banner-fail' : 'banner-pending'}`}>
      <div className="verification-banner-icon"><Icon name={reference ? 'book' : allPass ? 'shield' : data ? 'info' : 'clock'} size={27} /></div>
      <div className="verification-banner-copy"><div className="banner-eyebrow">{reference ? t('REFERENCE MODEL') : t('VERIFICATION STATUS')}<span>{snapshot ? t('Saved snapshot') : data ? reference ? t('Expected values') : t('Latest results') : t('Awaiting results')}</span></div><h2>{data ? reference ? t('Your reference model is ready.') : allPass ? t('Every tested pattern matches.') : t('Patterns need your attention.') : t('Your verification workspace is ready.')}</h2><p>{data ? reference ? t('Expected hashes are available. Run sign-off to collect measured simulation evidence.') : `${data.summary.passed} ${t('of')} ${total} ${t('patterns agree with the golden model.')}` : t('Connect your tools to start building verification evidence.')} {!reference && (hasSc ? t('Three representations, independently compared.') : t('SystemC evidence is incomplete.'))}</p></div>
      <button className="banner-button" onClick={() => onGo('scoreboard')}>{t('View scoreboard')}<Icon name="arrow" size={16} /></button>
    </section>
    <section className="metric-grid" aria-label={t('Project metrics')}>
      <Metric label={reference ? t('Reference patterns') : t('Patterns verified')} value={data ? String(reference ? total : data.summary.passed) : '—'} suffix={data && !reference ? ` / ${total}` : ''} detail={data ? reference ? t('Expected outputs from the golden model') : `${passRate}% ${t('of the test set passes')}` : t('Awaiting verification data')} icon="check-square" tone={allPass && !reference ? 'text-ok' : ''} />
      <Metric label={reference ? t('Pixels in test set') : t('Pixels compared')} value={data ? data.summary.total_pixels.toLocaleString() : '—'} detail={reference ? t('Ready for frame-level comparison') : t('Frame-level SHA-256 comparison')} icon="dashboard" />
      <Metric label={t('Design quality')} value={qor ? String(qor.score) : '—'} suffix={qor ? ' / 100' : ''} detail={qor ? `${t('Grade')} ${qor.grade} · ${qor.checks.filter(check => check.ok).length}/${qor.checks.length} ${t('checks passed')}` : t('Quality analysis unavailable')} icon="chart" />
      <Metric label={t('Archived sign-offs')} value={telemetry ? String(telemetry.count) : '—'} detail={telemetry?.count && telemetry.mean_score != null ? `${t('Mean score')} ${telemetry.mean_score}/100` : t('Run the full ladder to collect evidence')} icon="shield" />
    </section>
    <div className="overview-main-grid">
      <section className="dashboard-card gamma-card"><GammaChart data={data} /></section>
      <section className="dashboard-card evidence-card"><div className="card-heading"><div><h2>{t('The proof chain')}</h2><p>{t('Evidence at every representation.')}</p></div><Icon name="shield" size={18} /></div>
        <div className="evidence-chain">{models.map((model, index) => <div className="evidence-stage" key={model.title}><div className={`evidence-icon evidence-${model.status}`}><Icon name={model.icon} size={18} /></div><div className="evidence-stage-copy"><div><h3>{model.title}</h3><span className={`evidence-status evidence-status-${model.status}`}>{model.status === 'oracle' ? t('Reference') : model.status === 'pass' ? t('Matched') : model.status === 'fail' ? t('Mismatch') : t('No evidence')}</span></div><span className="evidence-language">{model.language}</span><p>{model.detail}</p></div>{index < models.length - 1 && <span className="evidence-connector" />}</div>)}</div>
        <div className="evidence-caveat"><Icon name="info" size={15} /><span>{t('A skipped stage is missing evidence, never a pass. 2-state simulation does not cover X/Z behavior.')}</span></div>
        <button className="card-link" onClick={() => onGo('flows')}>{t('Explore verification flows')}<Icon name="arrow" size={16} /></button>
      </section>
    </div>
    <section className="quick-action-grid" aria-label={t('Quick actions')}>{actions.map(action => <button className="quick-action" key={action.view} onClick={() => onGo(action.view)}><span className="quick-action-icon"><Icon name={action.icon} size={20} /></span><span><strong>{t(action.title)}</strong><small>{t(action.detail)}</small></span><Icon name="arrow" size={17} /></button>)}</section>
    <div className="overview-bottom-grid">
      <section className="dashboard-card patterns-card"><div className="card-heading"><div><h2>{t('Test patterns')}</h2><p>{reference ? t('Reference inputs, ready for simulation.') : t('The latest results from your comparison matrix.')}</p></div><button className="card-link" onClick={() => onGo('scoreboard')}>{t('View all')}<Icon name="arrow" size={15} /></button></div>
        <div className="table-wrap"><table className="grid overview-pattern-table"><thead><tr><th>{t('pattern')}</th><th>{t('status')}</th><th className="num">{t('pixels')}</th><th className="num">{t('mism.')}</th></tr></thead><tbody>{data?.patterns.slice(0, 6).map(pattern => <tr key={pattern.name}><td><button className="pattern-link mono" onClick={() => onPick(pattern)}><span className={`pattern-status-dot dot-${reference ? 'expected' : pattern.status}`} />{pattern.name}</button></td><td><StatusBadge status={reference ? 'expected' : pattern.status} /></td><td className="num">{pattern.pixels.toLocaleString()}</td><td className="num">{reference ? '—' : pattern.mismatches}</td></tr>)}</tbody></table>{!data && <div className="empty-inline">{t('Awaiting verification data')}</div>}</div>
        <div className="patterns-foot"><span><Icon name="check-square" size={14} />SHA-256 · {reference ? t('Reference hashes') : t('Bit-exact comparison')}</span><span>{total} {t('patterns')}</span></div>
      </section>
      <section className="dashboard-card design-card"><div className="card-heading"><div><h2>{t('Design under verification')}</h2><p>{t('Per-channel gamma correction')}</p></div><Icon name="chip" size={18} /></div><dl className="design-facts"><div><dt>{t('module')}</dt><dd>{data?.design.module ?? 'gamma'}</dd></div><div><dt>{t('precision')}</dt><dd>{data ? `${data.design.pixel_w}-bit` : '—'}</dd></div><div><dt>{t('LUT depth')}</dt><dd>{data?.design.lut_depth ?? '—'}</dd></div><div><dt>{t('throughput')}</dt><dd>1 {t('pixel / cycle')}</dd></div><div><dt>{t('handshake')}</dt><dd>ready / valid</dd></div></dl>
        <div className="design-resources"><button onClick={() => onGo('knowledge')}><Icon name="book" size={15} /><span>{t('Knowledge passages')}</span><b>{kb?.chunks ?? '—'}</b></button><button onClick={() => onGo('assistant')}><Icon name="sparkles" size={15} /><span>{t('Active agent skills')}</span><b>{skills ? `${skills.active.length}/${skills.skills.length}` : '—'}</b></button></div>
        <button className="secondary-button design-signoff" onClick={onRun} disabled={busy}><Icon name="play" size={13} />{t('Run sign-off')}</button>
      </section>
    </div>
    <div className="overview-footer"><Icon name="shield" size={14} /><span>{t('An executable oracle. Independent implementations. Inspectable evidence.')}</span><button onClick={() => onGo('help')}>{t('How verification works')}<Icon name="arrow" size={14} /></button></div>
  </div>
}
