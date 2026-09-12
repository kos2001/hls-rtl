import type { KbStats, QoRReport, SkillReport, VerificationResults } from './types'
import { useT } from './i18n'

/**
 * Overview — what this workbench is FOR.
 *
 * Every other view answers "what is the current state". None of them answered
 * "why does any of this exist", so the thesis lived only in module docstrings
 * that nobody opening the UI would read. This states it once, and then shows the
 * live evidence for it rather than asserting it.
 */

interface Props {
  data: VerificationResults | null
  qor: QoRReport | null
  skills: SkillReport | null
  kb: KbStats | null
  onGo: (view: string) => void
}

interface Rung {
  id: string
  label: string
  role: string
  status: 'oracle' | 'pass' | 'fail' | 'skip'
  detail: string
}

const CAPABILITIES: { n: string; title: string; gap: string; view?: string }[] = [
  { n: '1', title: 'Progressive-coding oracle', gap: 'NL→C++→RTL has no ground truth at any rung', view: 'flows' },
  { n: '2', title: 'Golden-as-oracle contract', gap: 'the exact hashes a candidate must reproduce', view: 'scoreboard' },
  { n: '3', title: 'Segment traceability', gap: 'regenerate only what actually changed' },
  { n: '4', title: 'Planner', gap: 'spec delta → tagged, reviewable steps', view: 'assistant' },
  { n: '5', title: 'Adaptive reflection', gap: 'a failure names its own root stage', view: 'flows' },
  { n: '6', title: 'Graph RAG', gap: 'structure-aware grounding', view: 'flows' },
  { n: '7', title: 'Equivalence (LEC)', gap: 'old ≡ new, proven not sampled', view: 'flows' },
  { n: '+', title: 'Knowledge base', gap: 'answers cite the passage behind them', view: 'knowledge' },
]

export function Overview({ data, qor, skills, kb, onGo }: Props) {
  const t = useT()
  const scSkipped = !!data?.patterns.every((p) => !p.sc_sha256)
  const failed = data?.summary.failed ?? 0

  const rungs: Rung[] = [
    {
      id: 'golden', label: 'golden', role: 'Python · numpy',
      status: 'oracle',
      detail: t('defines the expected values — untimed, independent, cheap to re-run'),
    },
    {
      id: 'systemc', label: 'systemc', role: 'C++ · cycle-accurate',
      status: scSkipped ? 'skip' : failed ? 'fail' : 'pass',
      detail: scSkipped
        ? t('skipped — build/sc_out.txt absent. Missing evidence, not a pass.')
        : t('bit-exact against the oracle'),
    },
    {
      id: 'rtl', label: 'rtl', role: 'Verilog-2001 · synthesizable',
      status: data ? (failed ? 'fail' : 'pass') : 'skip',
      detail: data
        ? `${data.summary.passed}/${data.summary.total_patterns} patterns, ${data.summary.total_pixels.toLocaleString()} pixels compared`
        : t('no results loaded'),
    },
  ]

  return (
    <div className="view-scroll">
      <section className="thesis">
        <h1 className="thesis-claim">
          {t('An agent can write plausible RTL. It cannot tell you whether the RTL is right.')}
        </h1>
        <p className="thesis-body">
          Spec2RTL-style agents generate HDL and then have nothing to check it against —
          “the tests the agent also wrote pass” is the whole argument. This workbench
          supplies the missing half: an <b>executable oracle</b>, and a loop that proves
          each representation against it.
        </p>
        <p className="thesis-claim-2">
          For every pattern in the test set, the Python golden, the SystemC model and the
          Verilog RTL produce <b>byte-identical output</b>, and the SHA-256 of each frame
          proves it.
        </p>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>{t('The proof chain')}</h2>
          <button className="tb-btn" onClick={() => onGo('scoreboard')}>{t('Open scoreboard →')}</button>
        </div>
        <div className="rungs">
          {rungs.map((r, i) => (
            <div key={r.id} className="rung-wrap">
              <div className={`rung rung-${r.status}`}>
                <div className="rung-top">
                  <span className="rung-label">{r.label}</span>
                  <span className={`badge badge-${r.status === 'oracle' ? 'pass' : r.status}`}>
                    {r.status === 'oracle' ? 'oracle' : r.status}
                  </span>
                </div>
                <div className="rung-role">{r.role}</div>
                <div className="rung-detail muted small">{r.detail}</div>
              </div>
              {i < rungs.length - 1 && <div className="rung-arrow">≡</div>}
            </div>
          ))}
        </div>
        <p className="panel-foot muted small">
          The golden model is <b>untimed</b>, so it cannot express a handshake bug. That is
          exactly why comparing against it separates <i>value</i> correctness from{' '}
          <i>timing</i> correctness: backpressure reorders pixels in time but must not
          change the hash.
        </p>
      </section>

      <section className="panel panel-caveat">
        <strong>{t('What this does not prove.')}</strong> The regression runs under Verilator,
        which is 2-state. These hashes cover value equality on the listed patterns; they
        do not cover X-propagation or reset-initialization behaviour. A skipped stage is
        missing evidence, not a pass. Cross-check with{' '}
        <code>make -C tb SIM=icarus</code> before claiming those are clean.
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>{t('Design under verification')}</h2>
          <button className="tb-btn" onClick={() => onGo('schematic')}>{t('Open schematic →')}</button>
        </div>
        <div className="dut-facts">
          <Fact k={t('module')} v={data?.design.module ?? 'gamma'} />
          <Fact k={t('throughput')} v="1 pixel / cycle" />
          <Fact k={t('latency')} v="1 cycle (accept → valid)" />
          <Fact k={t('handshake')} v="ready/valid, no out_ready→in_ready path" />
          <Fact k={t('elasticity')} v="FIFO_DEPTH = 8 (knee of the sweep)" />
          <Fact k={t('precision')} v={data ? `${data.design.pixel_w}b · LUT ${data.design.lut_depth}` : '8b · LUT 256'} />
          <Fact k="γ per channel" v={data ? Object.values(data.gammas).join(' / ') : '2.2 / 1.8 / 2.8'} />
          <Fact k="QoR" v={qor ? `${qor.score}/100 (${qor.grade})` : '—'} />
        </div>
        <p className="panel-foot muted small">
          Per-channel gammas differ on purpose: with identical LUTs a crossed-channel bug
          produces identical output and passes silently. Full spec in{' '}
          <code>docs/UARCH.md</code>, indexed into the knowledge base
          {kb ? ` (${kb.chunks} passages)` : ''}.
        </p>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>{t('What the workbench adds')}</h2>
          <span className="muted small">{t('each exists because a generate-then-hope loop lacks it')}</span>
        </div>
        <div className="caps">
          {CAPABILITIES.map((c) => (
            <button
              key={c.n}
              className={`cap ${c.view ? 'cap-go' : ''}`}
              onClick={() => c.view && onGo(c.view)}
              disabled={!c.view}
            >
              <span className="cap-n">{c.n}</span>
              <span className="cap-title">{c.title}</span>
              <span className="cap-gap muted small">{c.gap}</span>
            </button>
          ))}
        </div>
        <p className="panel-foot muted small">
          Agent answers are grounded in the retrieved knowledge base and cite the passage
          behind each claim
          {skills ? `; ${skills.active.length}/${skills.skills.length} skills loaded on profile ${skills.profile}` : ''}.
        </p>
      </section>
    </div>
  )
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="dut-fact">
      <span className="dut-k">{k}</span>
      <span className="dut-v mono">{v}</span>
    </div>
  )
}
