import { useT } from '../i18n'
import { Sparkline } from '../ui'
import type { SignoffReport, Telemetry } from '../types'
import { StatusBadge } from './shared'
import { Icon } from '../components/Icon'
import { Busy, useElapsed } from '../ui'

export function SignoffView({ report, telemetry, busy, error, disabled, onRun }: {
  report: SignoffReport | null; telemetry: Telemetry | null
  busy: boolean; error?: boolean; disabled?: boolean; onRun: () => void
}) {
  const t = useT()
  const elapsed = useElapsed(busy)
  const hist = (telemetry?.history ?? []).map((h) => h.score).filter((s): s is number => s != null)
  return (
    <div className="view-scroll">
      {error && <div className="snapshot-notice" role="alert"><Icon name="info" size={18} /><span>{t('Sign-off could not complete. Open the transcript for details and retry.')}</span></div>}
      <div className="panel">
        <div className="panel-head">
          <h2>{t('Sign-off Ladder')}</h2>
          <button className="btn-run" onClick={onRun} disabled={busy || disabled}>
            {busy ? `■ ${t('Running…')}` : `▶ ${t('Run sign-off')}`}
          </button>
        </div>
        <p className="muted small">
          {t('Run lint, design checks, synthesis, and simulation. Each stage reports its own result.')}
        </p>
        {hist.length >= 2 && (
          <div className="trend-row">
            <span className="muted small">{t('score trend')}</span><Sparkline values={hist} />
          </div>
        )}
        {report && (
          <>
            <div className={`verdict verdict-${report.verdict}`}>
              VERDICT: {report.verdict} · {report.grade} ({report.score}/100)
            </div>
            <div className="table-wrap">
              <table className="grid">
                <thead><tr><th>{t('stage')}</th><th>{t('status')}</th><th>{t('gating')}</th><th>{t('detail')}</th></tr></thead>
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
        {busy && <Busy label={t('Running sign-off…')} sec={elapsed} hint="lint → design → synthesize → simulate" />}
        {!report && !busy && <div className="signoff-empty"><span className="signoff-empty-icon"><Icon name="shield" size={32} /></span><h3>{t('Collect evidence for your design')}</h3><p>{t('No sign-off run yet')}</p><div className="signoff-steps">{['lint', 'design', 'synthesize', 'simulate'].map((step, i) => <span key={step}><b>{String(i + 1).padStart(2, '0')}</b>{step}</span>)}</div></div>}
      </div>
    </div>
  )
}
