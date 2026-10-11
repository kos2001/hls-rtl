import type { VerificationResults } from './types'

/** Older snapshots predate provenance metadata and contain expected hashes only. */
export function isReference(data: VerificationResults | null): boolean {
  return !!data && data.evidence_kind !== 'regression'
}
