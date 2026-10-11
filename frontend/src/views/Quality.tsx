import { useT } from '../i18n'
import type { QoRReport } from '../types'

export function Quality({ qor }: { qor: QoRReport | null }) {
  const t = useT()
  if (!qor) return <div className="pane-empty muted">{t('No QoR report — reload from the toolbar.')}</div>
  const m = qor.metrics
  const errs = qor.checks.filter((c) => !c.ok && c.severity === 'error')
  const warns = qor.checks.filter((c) => !c.ok && c.severity === 'warn')
  return (
    <div className="view-scroll">
      <div className="panel">
        <div className="panel-head"><h2>{t('Design Quality (QoR)')}</h2></div>
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
          <h2>{t('Design Rule Checks')}</h2>
          <span className="muted small">
            {errs.length} error · {warns.length} warning · {qor.checks.length} total
          </span>
        </div>
        <div className="table-wrap">
          <table className="grid">
            <thead><tr><th>{t('severity')}</th><th>{t('rule')}</th><th>{t('result')}</th><th>{t('detail')}</th></tr></thead>
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
