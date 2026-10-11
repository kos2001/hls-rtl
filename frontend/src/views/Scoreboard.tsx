import { useState } from 'react'
import { Icon } from '../components/Icon'
import { isReference } from '../evidence'
import { useT } from '../i18n'
import type { PatternResult, VerificationResults } from '../types'
import { Sha, StatusBadge } from './shared'

export function Scoreboard({ data, onPick }: { data: VerificationResults; onPick: (pattern: PatternResult) => void }) {
  const t = useT()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const reference = isReference(data)
  const allPass = data.summary.total_patterns > 0 && data.summary.failed === 0 && data.summary.passed === data.summary.total_patterns
  const patterns = data.patterns.filter(pattern => pattern.name.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || pattern.status === 'fail'))
  return <div className="view-scroll">
    {reference && <div className="snapshot-notice"><Icon name="info" size={18} /><span><strong>{t('Reference preview')}. </strong>{t('These are expected outputs, not measured RTL results. Run sign-off to verify the implementation.')}</span></div>}
    <div className="stat-strip">
      <div className={`stat ${!reference && allPass ? 'stat-ok' : !reference ? 'stat-fail' : ''}`}><div className="stat-value">{reference ? t('Expected') : allPass ? 'PASS' : data.summary.total_patterns ? 'FAIL' : '—'}</div><div className="stat-label">{reference ? t('Reference preview') : t('scoreboard verdict')}</div></div>
      <div className="stat"><div className="stat-value">{reference ? data.summary.total_patterns : `${data.summary.passed}/${data.summary.total_patterns}`}</div><div className="stat-label">{reference ? t('Reference patterns') : t('patterns bit-exact')}</div></div>
      <div className="stat"><div className="stat-value">{data.summary.total_pixels.toLocaleString()}</div><div className="stat-label">{reference ? t('Pixels in test set') : t('pixels compared')}</div></div>
      <div className="stat"><div className="stat-value">{data.design.pixel_w}b / {data.design.lut_depth}</div><div className="stat-label">{t('pixel width / LUT depth')}</div></div>
    </div>
    <section className="panel scoreboard-panel"><div className="panel-head"><div><h2>{t('Pattern comparison')}</h2><p className="muted small">{patterns.length} / {data.patterns.length} {t('patterns')}</p></div><div className="pattern-filters"><label className="pattern-search"><Icon name="search" size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder={t('Filter patterns…')} aria-label={t('Filter patterns')} /></label>{!reference && <select value={filter} onChange={event => setFilter(event.target.value)} aria-label={t('status')}><option value="all">{t('All patterns')}</option><option value="fail">{t('Failed only')}</option></select>}</div></div>
      <div className="table-wrap"><table className="grid"><thead><tr><th>{t('pattern')}</th><th className="num">{t('pixels')}</th><th>{t('status')}</th><th className="num">{t('mism.')}</th><th>{reference ? t('Expected golden hashes') : 'golden sha-256'}</th><th>rtl sha-256</th><th>systemc sha-256</th></tr></thead><tbody>{patterns.map(pattern => <tr key={pattern.name} className="row-pick" onClick={() => onPick(pattern)}><td><button className="pattern-link mono" onClick={event => { event.stopPropagation(); onPick(pattern) }}><span className={`pattern-status-dot dot-${reference ? 'expected' : pattern.status}`} />{pattern.name}</button></td><td className="num">{pattern.pixels.toLocaleString()}</td><td><StatusBadge status={reference ? 'expected' : pattern.status} /></td><td className="num">{reference ? '—' : pattern.mismatches}</td><td><Sha value={pattern.golden_sha256} /></td><td>{reference ? <span className="muted">{t('Not measured')}</span> : <Sha value={pattern.rtl_sha256} />}</td><td>{reference ? <span className="muted">{t('Not measured')}</span> : <Sha value={pattern.sc_sha256} />}</td></tr>)}</tbody></table>{!patterns.length && <div className="pane-empty"><Icon name="search" size={24} /><p>{t('No patterns match your filters.')}</p><button className="secondary-button" onClick={() => { setQuery(''); setFilter('all') }}>{t('Reset filters')}</button></div>}</div>
      <p className="panel-foot muted small">{data.source}</p>
    </section>
    <div className="panel panel-caveat"><strong>{t('What this does not prove.')}</strong> {t('A skipped stage is missing evidence, never a pass. 2-state simulation does not cover X/Z behavior.')} <code>make -C tb SIM=icarus</code></div>
  </div>
}
