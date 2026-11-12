// Orders the candidates on the current Merge Review page for the one sort the
// API does not offer yet. Pure, so the page decides only *which* sort.
//
// `candidates` arrive in the API's order, which for this sort is newest first.
// "status" groups work still to do first -- candidates, then denied, then
// approved -- newest first within each. Any other sort keeps the API's order.

const STATUS_ORDER = ["PENDING", "DENIED", "APPROVED"];

function statusRank(status) {
  const index = STATUS_ORDER.indexOf(status);
  return index === -1 ? STATUS_ORDER.length : index;
}

export function sortCandidates(candidates, sort) {
  if (sort !== "status") return [...candidates];
  // Array.prototype.sort is stable, so equal statuses keep the API's
  // newest-first order.
  return [...candidates].sort(
    (a, b) => statusRank(a.status) - statusRank(b.status),
  );
}
