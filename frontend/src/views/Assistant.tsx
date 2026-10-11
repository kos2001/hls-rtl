import { ChatPanel, PlanTab } from '../PlanAsk'
import type { SkillReport } from '../types'

export default function Assistant({ gatewayReady, skills }: { gatewayReady: boolean; skills: SkillReport | null }) {
  return <div className="view-scroll"><PlanTab gatewayReady={gatewayReady} /><ChatPanel gatewayReady={gatewayReady} skills={skills} /></div>
}
