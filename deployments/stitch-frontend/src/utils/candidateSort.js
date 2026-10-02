// Orders the Merge Review queue. Pure, so the page decides only *which* sort
// and supplies the names it has resolved so far.
//
// `candidates` arrive in the API's order, which is newest first, so "newest"
// keeps it and "oldest" reverses it. The name sorts compare the queue's
// display names, ignoring case and accents ("Ábalos" sorts as "Abalos"), and
// break ties newest first. A candidate whose name has not loaded yet (absent
// from `namesById`) cannot be placed, so those go at the end, newest first,
// until their names arrive.

// Pinned to English rather than the browser's language: some locales treat
// accented letters as letters of their own (Swedish sorts "ä" after "z"), which
// would break the accent-insensitive order the control promises.
const nameCollator = new Intl.Collator("en", { sensitivity: "base" });

export function sortCandidates(candidates, sort, namesById) {
  if (sort === "oldest") return [...candidates].reverse();
  if (sort !== "name-asc" && sort !== "name-desc") return [...candidates];

  const direction = sort === "name-desc" ? -1 : 1;
  const apiOrder = new Map(
    candidates.map((candidate, index) => [candidate.id, index]),
  );

  return [...candidates].sort((a, b) => {
    const nameA = namesById.get(a.id);
    const nameB = namesById.get(b.id);
    const aLoaded = nameA != null;
    const bLoaded = nameB != null;

    if (aLoaded !== bLoaded) return aLoaded ? -1 : 1;
    if (aLoaded) {
      const byName = nameCollator.compare(nameA, nameB) * direction;
      if (byName !== 0) return byName;
    }
    return apiOrder.get(a.id) - apiOrder.get(b.id);
  });
}
