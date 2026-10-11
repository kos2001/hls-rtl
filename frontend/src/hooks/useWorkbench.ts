import { useCallback, useEffect, useRef, useState } from 'react'
import { isReference } from '../evidence'
import { api } from '../api'
import { log, traced } from '../log'
import type { NavSelection } from '../Navigator'
import type { Health, KbStats, QoRReport, SignoffReport, SkillReport, Telemetry, VerificationResults } from '../types'

/** Owns workspace data and serializes refresh/sign-off to avoid stale responses. */
export function useWorkbench() {
  const [health, setHealth] = useState<Health | null>(null)
  const [data, setData] = useState<VerificationResults | null>(null)
  const [qor, setQor] = useState<QoRReport | null>(null)
  const [skills, setSkills] = useState<SkillReport | null>(null)
  const [kb, setKb] = useState<KbStats | null>(null)
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null)
  const [signoff, setSignoff] = useState<SignoffReport | null>(null)
  const [signoffError, setSignoffError] = useState(false)
  const [sel, setSel] = useState<NavSelection | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const operation = useRef(false)

  const loadAll = useCallback(async () => {
    if (operation.current) return
    operation.current = true
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
          else if (isReference(v)) log.note('ORACLE', `${v.summary.total_patterns} reference patterns; measured RTL evidence requires sign-off`)
          else log.info('SCOREBOARD', `${v.summary.passed}/${v.summary.total_patterns} patterns bit-exact (${v.summary.total_pixels.toLocaleString()} px)`)
          if (v.resultMode === 'snapshot') log.warn('SCOREBOARD', 'Bundled snapshot; no live verification evidence available')
          return { status: v.resultMode === 'snapshot' || isReference(v) ? 'skip' : f ? 'fail' : 'pass' }
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
        }).then((v) => setQor(v)),
      api.skills().then((s) => {
        setSkills(s)
        log.info('SKILLS', `profile ${s.profile}: ${s.active.length}/${s.skills.length} loaded`)
        for (const m of s.missing) log.warn('SKILLS', `${m}: not installed in the serving profile — agent cannot load it`)
      }).catch(() => setSkills(null)),
      api.telemetry('signoff').then(setTelemetry).catch(() => setTelemetry(null)),
      api.kbStats().then((k) => {
        setKb(k)
        log.info('KB', `${k.chunks} passages indexed (${k.pinned} pinned), ${k.terms} terms`)
      }).catch(() => setKb(null)),
    ])
    setUpdatedAt(new Date())
    operation.current = false
    setBusy(null)
  }, [])

  useEffect(() => { void loadAll() }, [loadAll])

  async function runSignoff() {
    if (operation.current) return
    operation.current = true
    setBusy('signoff')
    setSignoffError(false)
    setSignoff(null)
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
    else setSignoffError(true)
    api.telemetry('signoff').then(setTelemetry).catch(() => {})
    operation.current = false
    setBusy(null)
  }

  return { health, data, qor, skills, kb, telemetry, signoff, signoffError, sel, setSel, busy, updatedAt, loadAll, runSignoff }
}
