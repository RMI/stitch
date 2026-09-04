# Stitch Frontend

React frontend application styled with Tailwind CSS and built with Vite.

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Scripts](#scripts)
- [Configuration](#configuration)
- [API](#api)
- [Testing](#testing)
- [Queries](#queries)
- [Resource Detail View](#resource-detail-view)

## Tech Stack

- **React 19.2.0** - UI library
- **Vite 7.2.4** - Build tool and dev server
- **Tailwind CSS 4.1.18** - Utility-first CSS framework
- **React Router DOM 7** - Client-side routing
- **TanStack Query 5** - Server state and cache management
- **Vitest 3.2.4** - Unit testing framework
- **React Testing Library 16.3.1** - React component testing utilities

## Project Structure

```text
stitch-frontend/
├── mockData/                    # Static JSON fixtures for mock data mode
│   └── og_field_resources.json
├── public/                      # Static assets and runtime config
│   └── config.json              # Browser runtime config (committed local defaults)
├── src/
│   ├── auth/                    # Auth0 integration and gate component
│   ├── components/              # Shared UI components
│   │   ├── FieldCard.jsx        # Field value card + FieldGrid layout
│   │   ├── FilterBar.jsx        # Filter dropdown row + active chips
│   │   ├── FilterDropdown.jsx   # Multi-select dropdown with counts
│   │   ├── ResourcesTable.jsx   # Sortable resources table
│   │   ├── ResourcesView.jsx    # Resources list page section
│   │   ├── ResourceView.jsx     # Single resource fetch section
│   │   ├── SectionHeader.jsx    # Titled section divider
│   │   └── SourceMixBar.jsx     # Data source proportion bar
│   ├── config/
│   │   ├── env.js               # Runtime config loader/accessors + build metadata
│   │   └── filters.js           # Filter field definitions (FILTER_FIELDS, EMPTY_FILTERS)
│   ├── hooks/
│   │   ├── useAuthenticatedQuery.js
│   │   └── useResources.js      # useResources / useResource (real + mock implementations)
│   ├── constants/
│   │   ├── fieldMeta.js         # Field display labels and section groupings (FIELD_META)
│   │   └── sourceMeta.js        # Data source labels and colors (SOURCES, SOURCE_COLORS, SOURCE_LABELS)
│   ├── pages/
│   │   ├── HomePage.jsx         # "/" — ResourcesView + ResourceView
│   │   └── ResourceDetailPage.jsx  # "/resources/:id" — full resource detail view
│   ├── queries/                 # TanStack Query key factory and definitions
│   ├── test/                    # Test setup and shared utilities
│   ├── App.jsx                  # Route definitions
│   ├── main.jsx                 # App entry point with async bootstrap
│   └── index.css                # Global styles and Tailwind imports
├── index.html
├── vite.config.js               # envDir points to project root for .env
├── eslint.config.js
└── package.json
```

## Scripts

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Create production build
npm run build

# Preview the production build locally
npm run preview

# Run ESLint
npm run lint

# Run tests
npm test

# Run tests with UI
npm run test:ui

# Run tests with coverage report
npm run test:coverage
```

## Configuration

The frontend uses a split configuration model:

- **Runtime browser config** is loaded from `public/config.json`
- **Build metadata** is injected at build time via Vite env vars
- **Compile-time feature flags** remain in env files when needed

### Runtime browser config

At startup, `src/config/env.js` fetches `/config.json` before the app renders.

This file contains public, deployment-specific browser settings such as:

- `appEnv`
- `apiUrl`
- `entityLinkageUrl`
- `auth0Domain`
- `auth0ClientId`
- `auth0Audience`

A committed `public/config.json` provides local development defaults. Preview and production deployments should replace or generate that file during deployment.

Example:

```json
{
  "appEnv": "local",
  "apiUrl": "http://localhost:8000/api/v1",
  "entityLinkageUrl": "http://localhost:8001/api/v1",
  "auth0Domain": "rmi-spd.us.auth0.com",
  "auth0ClientId": "TS1V1soQbccAV1sitFFCfUaIlSwHD2S2",
  "auth0Audience": "https://stitch-api.local"
}
```

### Build-time values

Build metadata remains build-time configuration. These values are read from `import.meta.env` during the Vite build and surfaced through `config.build`:

- `VITE_APP_VERSION`
- `VITE_BUILD_ID`
- `VITE_GIT_SHA`
- `VITE_NODE_VERSION`
- `VITE_VITE_VERSION`
- `VITE_BUILD_TIME`

These are useful for colophon/build-info UI and deployment debugging.

### Compile-time flags

`VITE_USE_MOCK_DATA` is still a compile-time flag.

Set it in `.env.local` when you want the UI to use mock resources instead of the real API:

```dotenv
VITE_USE_MOCK_DATA=true
```

The flag is read at module-load time in `src/hooks/useResources.js`, so it must be present when the frontend is built or started.

### Deployment notes

For preview and production deployments:

1. Generate or replace `public/config.json` with environment-specific values
2. Build the frontend
3. Deploy static assets
4. Serve `/config.json` with `Cache-Control: no-store`

If you need to generate the file after the build, update `dist/config.json` instead; changing `public/config.json` post-build does not affect the already-built artifacts.

`config.json` is public and must not contain secrets.

## Mock Data

The app supports a mock data mode for local UI development. When enabled, `useResources()` and `useResource(id)` serve data directly from `mockData/og_field_resources.json` instead of hitting the real API.

**Note:** mock mode only affects the data hooks. `AuthGate` still enforces Auth0 authentication, so you must still have Auth0 configured to reach any page. If you want to develop without Auth0, that requires a separate change to bypass `AuthGate`.

**Toggle:** set `VITE_USE_MOCK_DATA` in your `.env.local` file:

```dotenv
VITE_USE_MOCK_DATA=true
```

The flag is read at compile time in `src/hooks/useResources.js`:

```js
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";
```

The real and mock implementations are separate functions selected once at module evaluation time — no conditional hook calls at render time.

## API

To temporarily run the API in development mode, outside Docker:
`uv run --package stitch-api stitch-api`

To temporarily seed the resources/ endpoint with data:
`node seed-resources.js`

## Testing

This project uses **Vitest** for unit testing and **React Testing Library** for component testing.

```bash
# Run tests in watch mode
npm test

# Run tests once
npm test -- --run

# Run tests with UI interface
npm run test:ui

# Generate coverage report
npm run test:coverage
```

### Writing Tests

Test files should be placed next to the component they test with a `.test.jsx` or `.test.js` extension.

Use `renderWithQueryClient` from `src/test/utils.jsx` instead of `render` directly — it wraps the component in both a `QueryClientProvider` and a `MemoryRouter`, which most components require:

```javascript
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithQueryClient } from "../test/utils";
import MyComponent from "./MyComponent";

describe("MyComponent", () => {
  it("renders correctly", () => {
    renderWithQueryClient(<MyComponent />);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });
});
```

### Mocking Data Hooks

Components that fetch data use `useResource` or `useResources` from `src/hooks/useResources.js`. Mock these hooks rather than the network — this keeps tests independent of whether the app is in real API or mock data mode:

```javascript
import { vi, beforeEach } from "vitest";
import { useResource } from "../hooks/useResources";

vi.mock("../hooks/useResources");

const defaultHookReturn = {
  data: null,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

beforeEach(() => {
  vi.mocked(useResource).mockReturnValue({
    ...defaultHookReturn,
    refetch: vi.fn(),
  });
});
```

Override the mock per-test to simulate loading, error, or success states:

```javascript
it("shows a loading indicator", () => {
  vi.mocked(useResource).mockReturnValue({
    ...defaultHookReturn,
    isLoading: true,
  });
  renderWithQueryClient(<MyComponent />);
  expect(screen.getByText(/loading/i)).toBeInTheDocument();
});
```

### Testing Utilities

`src/test/utils.jsx` exports:

| Export                              | Description                                                                                    |
| ----------------------------------- | ---------------------------------------------------------------------------------------------- |
| `renderWithQueryClient(ui)`         | Renders inside `QueryClientProvider` + `MemoryRouter`; returns `{ queryClient, ...rtlResult }` |
| `auth0TestDefaults`                 | Default Auth0 mock state (authenticated); spread and override for auth tests                   |
| `createMockResponse(data, options)` | Builds a mock `fetch` response object                                                          |
| `createMockError(status)`           | Builds a mock error `fetch` response                                                           |

Additional libraries:

- **@testing-library/jest-dom** — custom DOM matchers (e.g. `toBeInTheDocument`, `toHaveStyle`)
- **@testing-library/user-event** — user interaction simulation
- **jsdom** — DOM environment for Node.js

Test setup is located in `src/test/setup.js` and runs automatically before each test file.

## Queries

This project uses the query key factory pattern recommended by TanStack Query for managing React Query cache keys.

### Structure

```text
src/
├── queries/
│   ├── api.js          # API fetch functions
│   └── resources.js    # Resource query keys and definitions
└── hooks/
    └── useResources.js # Resource hooks (useResource, useResources)
```

### Pattern

#### Query Keys (Hierarchical)

Query keys are organized hierarchically for easy invalidation:

```js
export const resourceKeys = {
  all: ["resources"], // ['resources']
  lists: () => [...resourceKeys.all, "list"], // ['resources', 'list']
  list: (filters) => [...resourceKeys.lists(), filters], // ['resources', 'list', filters]
  details: () => [...resourceKeys.all, "detail"], // ['resources', 'detail']
  detail: (id) => [...resourceKeys.details(), id], // ['resources', 'detail', id]
};
```

#### Query Definitions

Query configurations are defined once and reused:

```js
export const resourceQueries = {
  list: () => ({
    queryKey: resourceKeys.lists(),
    queryFn: getResources,
    enabled: false,
  }),

  detail: (id) => ({
    queryKey: resourceKeys.detail(id),
    queryFn: () => getResource(id),
    enabled: false,
  }),
};
```

### Usage

#### In Hooks

```js
// src/hooks/useResources.js
export const useResources = USE_MOCK_DATA ? useResourcesMock : useResourcesReal;
export const useResource = USE_MOCK_DATA ? useResourceMock : useResourceReal;
```

Each named function always calls the same hooks unconditionally, satisfying React's rules of hooks. The choice between real and mock is made once at module evaluation time.

Consumers import the hooks without knowing which implementation is active:

```js
import { useResources, useResource } from "../hooks/useResources";
```

#### In Components (Cache Manipulation)

```js
import { useQueryClient } from "@tanstack/react-query";
import { resourceKeys } from "../queries/resources";

function MyComponent() {
  const queryClient = useQueryClient();

  // Reset a specific resource
  const clearOne = (id) => {
    queryClient.resetQueries({ queryKey: resourceKeys.detail(id) });
  };

  // Invalidate all resource details (but not lists)
  const invalidateAllDetails = () => {
    queryClient.invalidateQueries({ queryKey: resourceKeys.details() });
  };

  // Invalidate ALL resource queries (lists, details, everything)
  const invalidateEverything = () => {
    queryClient.invalidateQueries({ queryKey: resourceKeys.all });
  };
}
```

### Benefits

1. **Single source of truth** - All query keys defined in one place
2. **No typos** - Can't accidentally use `['resource']` vs `['resources']`
3. **Easy invalidation** - Invalidate groups of related queries hierarchically
4. **Type safety** - Easy to add TypeScript types
5. **Maintainability** - Query logic is centralized and reusable

### Examples from This Project

#### Clearing cache for a specific resource (ResourceView.jsx)

```js
import { resourceKeys } from "../queries/resources";

const handleClear = (id) => {
  queryClient.resetQueries({ queryKey: resourceKeys.detail(id) });
};
```

#### Clearing the resources list (ResourcesView.jsx)

```js
import { resourceKeys } from "../queries/resources";

const handleClear = () => {
  queryClient.setQueryData(resourceKeys.lists(), []);
};
```

### Adding New Queries

When adding new endpoints:

1. **Update the key factory** in `src/queries/[entity].js`:

```js
export const resourceKeys = {
  // ... existing keys
  mutations: () => [...resourceKeys.all, "mutation"],
  mutation: (id) => [...resourceKeys.mutations(), id],
};
```

2. **Add query definition**:

```js
export const resourceQueries = {
  // ... existing queries
  mutation: (id) => ({
    queryKey: resourceKeys.mutation(id),
    queryFn: () => mutateResource(id),
  }),
};
```

3. **Use in hook**:

```js
export function useMutateResource(id) {
  return useQuery(resourceQueries.mutation(id));
}
```

### Reference

- [TanStack Query Docs: Query Keys](https://tanstack.com/query/latest/docs/react/guides/query-keys)
- [Effective React Query Keys](https://tkdodo.eu/blog/effective-react-query-keys)

## Filters

The resources table supports multi-select filters with OR-within / AND-across logic (e.g. region = "Asia" OR "Europe", AND basin = "Arabian").

Filter fields are configured in one place:

```js
// src/config/filters.js
export const FILTER_FIELDS = [
  { key: "region", label: "Region" },
  { key: "state_province", label: "State/Province" },
  { key: "basin", label: "Basin" },
];
```

Add a new filter by appending an entry. The `key` must match the field name on the resource object. Option counts are computed statically from the full dataset on load.

Active filter selections are displayed as removable chips beneath the dropdowns. Filters are applied client-side in `ResourcesView` via `applyFilters()`. This function is a pure utility designed to be lifted server-side when pagination is introduced.

## Deployment: Azure Static Web Apps

### Prerequisites

- API deployed and reachable
- Auth0 application created
- GitHub repository with Actions enabled

---

### Runtime deployment model

The frontend bundle does not need environment-specific API/Auth values baked in at build time.

Instead, deployment should provide `public/config.json` with the environment-specific browser config values, then deploy the static assets. This lets the same frontend bundle shape work across local, preview, and production environments.

Recommended deploy sequence:

1. Write `public/config.json`
2. Build the frontend
3. Deploy the static site
4. Ensure `/config.json` is served with `Cache-Control: no-store`

---

### Canonical Values (Example)

```text
SWA_NAME=stitch-frontend-demo-02
RESOURCE_GROUP=STITCH-DEV-RG
API_URL=https://stitch-db-demo-02.<region>.azurecontainerapps.io/api/v1
ENTITY_LINKAGE_URL=https://stitch-entity-linkage-demo-02.<region>.azurecontainerapps.io/api/v1
AUTH0_DOMAIN=rmi-spd.us.auth0.com
AUTH0_CLIENT_ID=<public-client-id>
AUTH_AUDIENCE=https://stitch-api.local
```

Example runtime config:

```json
{
  "appEnv": "preview",
  "apiUrl": "https://stitch-db-demo-02.<region>.azurecontainerapps.io/api/v1",
  "entityLinkageUrl": "https://stitch-entity-linkage-demo-02.<region>.azurecontainerapps.io/api/v1",
  "auth0Domain": "rmi-spd.us.auth0.com",
  "auth0ClientId": "<public-client-id>",
  "auth0Audience": "https://stitch-api.local"
}
```

---

### Create Static Web App (Portal)

- Subscription: RMI-PROJECT-STITCH-SUB
- Resource Group: STITCH-DEV-RG
- Name: stitch-frontend-demo-02
- Plan: Free
- Source: Other (CI configured manually)

Deployment Authorization Policy: Deployment Token

---

### Configure GitHub Secret

Azure Portal → Manage Deployment Token

Add token as GitHub repository secret:

```text
AZURE_STATIC_WEB_APPS_DEPLOY_TOKEN
```

Push branch or open PR to trigger workflow.

---

### Expected State Before Auth0 Configuration

You should see the Stitch login page.

Attempting login will produce an Auth0 callback error.

This is expected until callback URLs are configured.

---

### Configure Auth0 Callback URLs

Auth0 Dashboard → Applications → Settings

Add your SWA URL to:

- Allowed Callback URLs
- Allowed Logout URLs
- Allowed Web Origins

The app passes `window.location.origin` as its `redirect_uri` and has no
dedicated callback route, so all three settings take the **bare origin** — no
trailing slash and no path. Auth0 matches these exactly; a trailing slash will
not match.

Example:

```text
https://<your-swa>.azurestaticapps.net
```

Because the origin is whatever the browser is on, **every hostname the app is
served from needs its own entry** — the generated `azurestaticapps.net`
hostname, each PR preview hostname, and any custom domain:

```text
https://stitch.rmi.org
```

Save.

Register a custom domain here _before_ pointing the lane's
`FRONTEND_PRODUCTION_URL` at it, or sign-in breaks on the first deploy. See
"Custom domains" in [`../CI_DEPLOYMENTS.md`](../CI_DEPLOYMENTS.md).

---

### Configure Auth0 for session persistence (refresh tokens)

The frontend keeps users signed in across page reloads by caching Auth0 tokens
in the browser's `localStorage` and renewing them with rotating refresh tokens
(see `src/AppProviders.jsx`: `cacheLocation="localstorage"` + `useRefreshTokens`).
For this to work reliably across browsers, the Auth0 tenant must actually issue
refresh tokens. If it does not, the SDK falls back to hidden-iframe silent
authentication, which Safari (ITP) and Chrome (third-party-cookie blocking)
block — so users are bounced to the login screen once their cached access token
expires. (This was the STIT-581 reload regression.)

Configure the following in the Auth0 Dashboard for the tenant serving this
environment.

**On the API** — Applications → APIs → _Stitch API_ → Settings → Access Settings:

- **Allow Offline Access: ON.** Required so Auth0 issues refresh tokens for this
  API (audience). The React SDK automatically requests the `offline_access`
  scope when refresh tokens are enabled; with _Allow Skipping User Consent_ on
  and the app marked First Party, users are not shown a consent prompt.

**On the Application** — Applications → Applications → _Stitch SPA_ → Settings:

- **Allow Refresh Token Rotation: ON.** Each refresh token is invalidated after
  use and exchanged for a new one, limiting the value of a leaked token —
  recommended when tokens live in `localStorage`. See
  [Refresh Token Rotation](https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation).
- **Rotation Overlap Period: 3 seconds.** A small non-zero leeway so concurrent
  requests, multiple open tabs, or a lost rotation response do not invalidate
  the session or trigger false-positive breach detection. `0` is stricter but
  fragile for SPAs. Auth0 documents the setting's purpose (leeway before reuse
  detection) but does not prescribe a value; 3s is our choice for SPA
  concurrency. See
  [Configure Refresh Token Rotation](https://auth0.com/docs/secure/tokens/refresh-tokens/configure-refresh-token-rotation).
- **Set Maximum Refresh Token Lifetime: ON** (required for rotation), e.g.
  `2592000` (30 days) — the absolute session ceiling, after which the user must
  re-authenticate regardless of activity.
- **Set Idle Refresh Token Lifetime: ON**, e.g. `1296000` (15 days) — the
  session ends after this much inactivity; each token use resets the idle clock.
  See
  [Configure Refresh Token Expiration](https://auth0.com/docs/secure/tokens/refresh-tokens/configure-refresh-token-expiration).

**Verify** it works: after logging in, open DevTools → Application → Local
Storage and confirm the `@@auth0spajs@@…` entry contains a `refresh_token` (the
`/oauth/token` network response should include one). To exercise the
cross-browser path specifically, test in Safari — log in, clear cookies (leaving
`localStorage` intact), then reload; you should remain authenticated via the
refresh token rather than the now-blocked silent-auth iframe.

> **Security note:** storing tokens in `localStorage` makes them readable by any
> script on the page, which raises the impact of an XSS vulnerability. Refresh
> token rotation shortens the window of a leaked token, but the primary defense
> is a Content-Security-Policy, which is not yet configured (tracked as a
> follow-up). See Auth0's
> [Token Storage](https://auth0.com/docs/secure/security-guidance/data-security/token-storage)
> guidance.

---

### Expected State After Auth0 Configuration

- Login succeeds.
- API calls fail with CORS error.

This is expected until API CORS is configured.

---

### Configure API CORS

Portal → Container App → Networking → CORS

- Enable credentials
- Max Age: 5
- Allowed Origins:
- Allowed Headers:

Apply changes.

---

### Final Expected State

- Login succeeds.
- API calls succeed.
- Authenticated resources load properly.

## Resource Detail View

`ResourceDetailPage` (`/resources/:id`) renders a full detail view for a single resource. It is organized into sections driven by two constants files.

### Constants

`**src/constants/sourceMeta.js**` — Data source registry:

```js
export const SOURCES = ["gem", "wm", "rmi", "llm"];

export const SOURCE_COLORS = {
  gem: "#4AE3D9",
  wm: "#3B44EC",
  rmi: "#F4A70B",
  llm: "#57A0FF",
};

export const SOURCE_LABELS = {
  gem: "GEM",
  wm: "Woodmac",
  rmi: "RMI",
  llm: "LLM",
};
```

`**src/constants/fieldMeta.js**` — Field display configuration. Maps API payload keys to a label and a `section` grouping used to populate each page section:

```js
export const FIELD_META = {
  name: { label: "Name", section: "identity" },
  country: { label: "Country", section: "identity" },
  // ...
  field_status: { label: "Field Status", section: "production" },
  discovery_year: { label: "Discovery Year", section: "production" },
  // ...
};
```
