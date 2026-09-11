// Single place that reads the API's merge-candidate staleness signal
// (`repointed_resources`), so a field rename is a one-file change.
//
// STIT-418: when an overlapping candidate is approved, a member of this
// candidate gets merged away (repointed). The API reports each moved member and
// the terminal resource it now lives on; an empty/absent list means the
// candidate is still valid.

/**
 * @param {{ repointed_resources?: Array<{resource_id: number, repointed_to: number}> }} [candidate]
 * @returns {{ isStale: boolean, moves: Array<{resource_id: number, repointed_to: number}> }}
 */
export function readCandidateStaleness(candidate) {
  // Degrade to "not stale" when the field is absent (older backend, or a payload
  // shape that predates this feature) rather than throwing.
  const moves = Array.isArray(candidate?.repointed_resources)
    ? candidate.repointed_resources
    : [];
  return { isStale: moves.length > 0, moves };
}
