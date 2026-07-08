import { useQuery } from "@tanstack/react-query";
import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { useConfig } from "../config/useConfig";
import { getAuthMe } from "../queries/api";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

// Cache the current user's claims for a while; permissions rarely change within
// a session and every gated control would otherwise refetch.
const PERMISSIONS_STALE_TIME = 5 * 60_000;

export const authKeys = {
  me: () => ["auth", "me"],
};

function useHasPermissionReal(permission) {
  const config = useConfig();
  const { data } = useAuthenticatedQuery({
    queryKey: authKeys.me(),
    queryFn: (fetcher) => getAuthMe(config, fetcher),
    staleTime: PERMISSIONS_STALE_TIME,
  });
  const permissions = data?.claims?.permissions ?? [];
  return permissions.includes(permission);
}

function useHasPermissionMock() {
  // Mock mode has no backend; grant everything so gated UI stays exercisable.
  useQuery({ queryKey: authKeys.me(), queryFn: () => Promise.resolve(null) });
  return true;
}

export const useHasPermission = USE_MOCK_DATA
  ? useHasPermissionMock
  : useHasPermissionReal;
