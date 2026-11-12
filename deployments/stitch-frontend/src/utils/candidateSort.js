import { candidateDisplayName } from "./mergeCandidateName";

// Orders the Merge Review queue. Pure, so the page decides only *which* sort.
//
// `candidates` arrive in the API's order, which is newest first, so "newest"
// keeps it and "oldest" reverses it. The name sorts compare the queue's
// display names the way the reviewer's browser language alphabetizes, and
// break ties newest first. "status" groups work still to do first --
// candidates, then denied, then approved -- newest first within each.

// The browser's language (no locale given), so each reviewer gets their own
// language's alphabetical order. Base sensitivity ignores case; in English it
// also ignores accents ("Ábalos" sorts as "Abalos"), while languages that treat
// some accented letters as letters of their own keep that (Swedish sorts "ä"
// after "z").
const nameCollator = new Intl.Collator(undefined, { sensitivity: "base" });

const STATUS_ORDER = ["PENDING", "DENIED", "APPROVED"];

function statusRank(status) {
  const index = STATUS_ORDER.indexOf(status);
  return index === -1 ? STATUS_ORDER.length : index;
}

export function sortCandidates(candidates, sort) {
  if (sort === "oldest") return [...candidates].reverse();
  if (sort === "status") {
    // Array.prototype.sort is stable, so equal statuses keep the API's
    // newest-first order.
    return [...candidates].sort(
      (a, b) => statusRank(a.status) - statusRank(b.status),
    );
  }
  if (sort !== "name-asc" && sort !== "name-desc") return [...candidates];

  const direction = sort === "name-desc" ? -1 : 1;
  const apiOrder = new Map(
    candidates.map((candidate, index) => [candidate.id, index]),
  );

  return [...candidates].sort((a, b) => {
    const byName =
      nameCollator.compare(candidateDisplayName(a), candidateDisplayName(b)) *
      direction;
    return byName || apiOrder.get(a.id) - apiOrder.get(b.id);
  });
}
