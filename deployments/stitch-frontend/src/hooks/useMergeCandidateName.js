import { useMergeSourceDetails } from "./useMergeSourceDetails";
import { pickCandidateName } from "../utils/mergeCandidateName";

// Resolves a merge candidate's display name from its source resources, using
// source-priority rules. Returns null while loading or if no source has a name.
export function useMergeCandidateName(endpoint, resourceIds) {
  const { data: details } = useMergeSourceDetails(endpoint, resourceIds);

  return details ? pickCandidateName(details) : null;
}
