# Stitch Frontend

React frontend application styled with Tailwind CSS and built with Vite.

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Scripts](#scripts)
- [API](#api)
- [Testing](#testing)
- [Queries](#queries)

## Tech Stack

- **React 19.2.0** - UI library
- **Vite 7.2.4** - Build tool and dev server
- **Tailwind CSS 4.1.18** - Utility-first CSS framework
- **React Router DOM 7** - Client-side routing
- **TanStack Query 5** - Server state and cache management
- **Vitest 3.2.4** - Unit testing framework
- **React Testing Library 16.3.1** - React component testing utilities

## Project Structure

```
stitch-frontend/
├── mockData/                    # Static JSON fixtures for mock data mode
│   └── og_field_resources.json
├── public/                      # Static assets
├── src/
│   ├── auth/                    # Auth0 integration and gate component
│   ├── components/              # Shared UI components
│   │   ├── FilterBar.jsx        # Filter dropdown row + active chips
│   │   ├── FilterDropdown.jsx   # Multi-select dropdown with counts
│   │   ├── ResourcesTable.jsx   # Sortable resources table
│   │   ├── ResourcesView.jsx    # Resources list page section
│   │   ├── ResourceView.jsx     # Single resource fetch section
│   │   └── SourceMixBar.jsx     # Data source proportion bar
│   ├── config/
│   │   ├── env.js               # Runtime environment config
│   │   └── filters.js           # Filter field definitions (FILTER_FIELDS, EMPTY_FILTERS)
│   ├── hooks/
│   │   ├── useAuthenticatedQuery.js
│   │   └── useResources.js      # useResources / useResource (real + mock implementations)
│   ├── pages/
│   │   ├── HomePage.jsx         # "/" — ResourcesView + ResourceView
│   │   └── ResourceDetailPage.jsx  # "/resources/:id"
│   ├── queries/                 # TanStack Query key factory and definitions
│   ├── test/                    # Test setup and shared utilities
│   ├── App.jsx                  # Route definitions
│   ├── main.jsx                 # App entry point with providers
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

## Mock Data

The app supports a mock data mode for local UI development. When enabled, `useResources()` and `useResource(id)` serve data directly from `mockData/og_field_resources.json` instead of hitting the real API.

**Note:** mock mode only affects the data hooks. `AuthGate` still enforces Auth0 authentication, so you must still have Auth0 configured to reach any page. If you want to develop without Auth0, that requires a separate change to bypass `AuthGate`.

**Toggle:** set `VITE_USE_MOCK_DATA` in your `.env.local` file:

```
VITE_USE_MOCK_DATA=true
```

The flag is read at compile time in `src/hooks/useResources.js`:

```js
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";
```

The real and mock implementations are separate functions selected once at module-load time — no conditional hook calls at render time.

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

**Example test:**

```javascript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MyComponent from "./MyComponent";

describe("MyComponent", () => {
  it("renders correctly", () => {
    render(<MyComponent />);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });
});
```

### Testing Utilities

The project includes:

- **@testing-library/react** - Component testing utilities
- **@testing-library/jest-dom** - Custom matchers for DOM elements
- **@testing-library/user-event** - User interaction simulation
- **jsdom** - DOM environment for Node.js

Test setup is located in `src/test/setup.js` and runs automatically before each test file.

## Queries

This project uses the query key factory pattern recommended by TanStack Query for managing React Query cache keys.

### Structure

```
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

### Canonical Values (Example)

```
SWA_NAME=stitch-frontend-demo-02
RESOURCE_GROUP=STITCH-DEV-RG
API_URL=https://stitch-db-demo-02.<region>.azurecontainerapps.io
AUTH0_DOMAIN=rmi-spd.us.auth0.com
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

```
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

Example:

```
https://<your-swa>.azurestaticapps.net/
https://<your-swa>.azurestaticapps.net/callback
```

Save.

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
- Allowed Origins: <SWA_URL>
- Allowed Headers: \*

Apply changes.

---

### Final Expected State

- Login succeeds.
- API calls succeed.
- Authenticated resources load properly.
