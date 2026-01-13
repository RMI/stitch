# Stitch Frontend

React frontend application styled with Tailwind CSS and built with Vite.

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

```

```
