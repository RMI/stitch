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
- **Vitest 3.2.4** - Unit testing framework
- **React Testing Library 16.3.1** - React component testing utilities

## Project Structure

```
stitch-frontend/
├── public/              # Static assets
├── src/
│   ├── test/           # Test setup and utilities
│   │   └── setup.js    # Vitest setup file
│   ├── App.jsx         # Root application component
│   ├── App.test.jsx    # App component tests
│   ├── main.jsx        # Application entry point
│   └── index.css       # Global styles and Tailwind imports
├── dist/               # Production build output
├── index.html          # HTML template
├── vite.config.js      # Vite configuration
├── vitest.config.js    # Vitest configuration
├── eslint.config.js    # ESLint configuration
└── package.json        # Dependencies and scripts
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
import { useQuery } from "@tanstack/react-query";
import { resourceQueries } from "../queries/resources";

export function useResource(id) {
  return useQuery(resourceQueries.detail(id));
}
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
