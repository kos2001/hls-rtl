import type { IconName } from './components/Icon'

export const NAVIGATION = [
  { id: 'overview', label: 'Overview', icon: 'dashboard', group: 'Workspace', description: 'Your design, verification evidence, and next steps at a glance.' },
  { id: 'scoreboard', label: 'Scoreboard', icon: 'check-square', group: 'Workspace', description: 'Compare every pattern against the independent golden model.' },
  { id: 'waveform', label: 'Waveform', icon: 'wave', group: 'Workspace', description: 'Inspect signal timing and ready/valid handshakes.' },
  { id: 'schematic', label: 'Schematic', icon: 'chip', group: 'Workspace', description: 'Explore the elaborated RTL and its connections.' },
  { id: 'quality', label: 'Quality', icon: 'chart', group: 'Verification', description: 'Review synthesis metrics, lint findings, and design rules.' },
  { id: 'signoff', label: 'Sign-off', icon: 'shield', group: 'Verification', description: 'Run the verification ladder and inspect each stage of evidence.' },
  { id: 'flows', label: 'Flows', icon: 'flow', group: 'Verification', description: 'Prove equivalence, trace failures, and inspect the proof chain.' },
  { id: 'improve', label: 'Improve', icon: 'sparkles', group: 'Intelligence', description: 'Find gaps in evidence and evaluate design improvements.' },
  { id: 'knowledge', label: 'Knowledge', icon: 'book', group: 'Intelligence', description: 'Search project knowledge with traceable source passages.' },
  { id: 'assistant', label: 'Assistant', icon: 'message', group: 'Intelligence', description: 'Plan design changes and ask questions grounded in your project.' },
  { id: 'help', label: 'Manual', icon: 'help', group: 'Resources', description: 'Everything you need to work confidently with Gamma.' },
] as const satisfies readonly { id: string; label: string; icon: IconName; group: string; description: string }[]

export type View = typeof NAVIGATION[number]['id']

export function isView(value: string): value is View {
  return NAVIGATION.some(item => item.id === value)
}
