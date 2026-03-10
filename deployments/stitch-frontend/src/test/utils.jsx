import { vi } from "vitest";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/**
 * Default return value for the mocked `useAuth0` hook (mirrors setup.js).
 * Spread and override in tests that need a different auth state:
 *
 *   vi.mocked(useAuth0).mockReturnValue({ ...auth0Defaults, isAuthenticated: false });
 */
export const auth0TestDefaults = {
  isAuthenticated: true,
  isLoading: false,
  error: null,
  user: { sub: "test-user-id", email: "test@example.com" },
  getAccessTokenSilently: vi.fn().mockResolvedValue("test-access-token"),
  loginWithRedirect: vi.fn(),
  logout: vi.fn(),
};

export function renderWithQueryClient(ui, options = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        cacheTime: 0,
      },
    },
    ...options.queryClientConfig,
  });

  return {
    ...render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
      </MemoryRouter>,
    ),
    queryClient,
  };
}

export function createMockResponse(data, options = {}) {
  return {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: async () => data,
  };
}

export function createMockError(status = 500) {
  return {
    ok: false,
    status,
    json: async () => ({}),
  };
}
