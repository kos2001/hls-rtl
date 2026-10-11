import { useT } from '../i18n'

export function Sha({ value }: { value: string | null }) {
  if (!value) return <span className="sha sha-none">— skipped</span>
  return <span className="sha" title={value}>{value.slice(0, 12)}…</span>
}

export function StatusBadge({ status }: { status: string }) {
  const t = useT()
  const cls = status === 'pass' ? 'pass' : status === 'fail' ? 'fail' : status === 'expected' ? 'expected' : 'skip'
  return <span className={`badge badge-${cls}`}>{status === 'expected' ? t('Expected') : status}</span>
}
