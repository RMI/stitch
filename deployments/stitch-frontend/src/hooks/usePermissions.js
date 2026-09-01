import { useAuthenticatedQuery } from "./useAuthenticatedQuery";
import { useConfig } from "../config/useConfig";

// Fetches the caller's auth claims once and exposes the permission list. This is
// the same claims payload ColophonPanel reads from `/auth/me`; here it is cached
// (long staleTime) so permission-gated affordances don't re-fetch per render.
export function usePermissions() {
  const config = useConfig();
  return useAuthenticatedQuery({
    queryKey: ["auth", "me", "permissions"],
    queryFn: async (fetcher) => {
      const response = await fetcher(`${config.apiBaseUrl}/auth/me`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        const error = new Error(`HTTP error! status: ${response.status}`);
        error.status = response.status;
        throw error;
      }
      const payload = await response.json();
      const permissions = payload?.claims?.permissions;
      return Array.isArray(permissions) ? permissions : [];
    },
    staleTime: 5 * 60_000,
  });
}

// True only once claims have loaded and include `permission`. Defaults to false
// while loading or on error, so gated controls stay hidden until confirmed.
export function useHasPermission(permission) {
  const { data } = usePermissions();
  return Array.isArray(data) && data.includes(permission);
}

// True only once claims have loaded and include every listed permission. Defaults
// to false while loading or on error, so gated controls stay hidden until
// confirmed.
export function useHasAllPermissions(permissions) {
  const { data } = usePermissions();
  return (
    Array.isArray(data) &&
    permissions.every((permission) => data.includes(permission))
  );
}
