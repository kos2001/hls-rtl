import { useState } from 'react'
import type { SkillReport, VerificationResults } from './types'

/**
 * Design navigator — the left-hand hierarchy pane of an EDA tool.
 *
 * It is a *browser*, not a menu: selecting a node drives the properties pane on
 * the right rather than switching views, which is how design browsers behave.
 * View switching stays in the tabs above the work area.
 */

export interface NavSelection {
  kind: 'design' | 'port' | 'pattern' | 'representation' | 'flow' | 'skill'
  id: string
  data?: unknown
}

interface Props {
  data: VerificationResults | null
  skills: SkillReport | null
  selected: NavSelection | null
  onSelect: (s: NavSelection) => void
}

const PORTS: [string, string][] = [
  ['clk', 'input  wire'], ['rst_n', 'input  wire (async, active-low)'],
  ['in_valid', 'input  wire'], ['in_ready', 'output wire'],
  ['in_r/g/b', 'input  wire [7:0]'],
  ['out_valid', 'output wire'], ['out_ready', 'input  wire'],
  ['out_r/g/b', 'output wire [7:0]'],
  ['lut_we', 'input  wire'], ['lut_ch', 'input  wire [1:0]'],
  ['lut_addr', 'input  wire [7:0]'], ['lut_wdata', 'input  wire [7:0]'],
]

function Group({ label, count, children, defaultOpen = true }:
  { label: string; count?: number | string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="nav-group">
      <button className="nav-group-head" onClick={() => setOpen(!open)}>
        <span className="nav-caret">{open ? '▾' : '▸'}</span>
        <span className="nav-group-label">{label}</span>
        {count != null && <span className="nav-count">{count}</span>}
      </button>
      {open && <div className="nav-children">{children}</div>}
    </div>
  )
}

export function Navigator({ data, skills, selected, onSelect }: Props) {
  const isSel = (kind: NavSelection['kind'], id: string) =>
    selected?.kind === kind && selected.id === id

  return (
    <nav className="navigator">
      <div className="nav-title">Design Navigator</div>

      <Group label={data?.design.module ?? 'gamma'} count="top">
        <button className={`nav-item ${isSel('design', 'top') ? 'nav-sel' : ''}`}
                onClick={() => onSelect({ kind: 'design', id: 'top', data })}>
          <span className="nav-icon nav-icon-mod">M</span>rtl/gamma.v
        </button>
        <Group label="ports" count={PORTS.length} defaultOpen={false}>
          {PORTS.map(([name, type]) => (
            <button key={name}
                    className={`nav-item ${isSel('port', name) ? 'nav-sel' : ''}`}
                    onClick={() => onSelect({ kind: 'port', id: name, data: type })}>
              <span className={`nav-icon ${type.startsWith('input') ? 'nav-icon-in' : 'nav-icon-out'}`}>
                {type.startsWith('input') ? 'I' : 'O'}
              </span>
              {name}
            </button>
          ))}
        </Group>
      </Group>

      <Group label="Representations" count={3}>
        {[
          ['golden', 'Python · reference oracle'],
          ['systemc', 'C++ · HLS intermediate'],
          ['rtl', 'Verilog-2001 · synthesizable'],
        ].map(([id, role]) => (
          <button key={id}
                  className={`nav-item ${isSel('representation', id) ? 'nav-sel' : ''}`}
                  onClick={() => onSelect({ kind: 'representation', id, data: role })}>
            <span className="nav-icon nav-icon-rep">R</span>{id}
          </button>
        ))}
      </Group>

      <Group label="Test Set" count={data?.patterns.length ?? 0}>
        {(data?.patterns ?? []).map((p) => (
          <button key={p.name}
                  className={`nav-item ${isSel('pattern', p.name) ? 'nav-sel' : ''}`}
                  onClick={() => onSelect({ kind: 'pattern', id: p.name, data: p })}>
            <span className={`nav-dot nav-dot-${p.status}`} />
            {p.name}
          </button>
        ))}
      </Group>

      <Group label="Agent Skills" count={`${skills?.active.length ?? 0}/${skills?.skills.length ?? 0}`}>
        {(skills?.skills ?? []).map((s) => (
          <button key={s.name}
                  className={`nav-item ${isSel('skill', s.name) ? 'nav-sel' : ''}`}
                  onClick={() => onSelect({ kind: 'skill', id: s.name, data: s })}
                  title={s.purpose}>
            <span className={`nav-dot ${s.installed ? 'nav-dot-pass' : 'nav-dot-skip'}`} />
            <span className="nav-trunc">{s.name}</span>
          </button>
        ))}
      </Group>
    </nav>
  )
}
