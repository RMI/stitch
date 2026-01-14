import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithQueryClient } from "./test/utils";
import App from "./App";

describe("App", () => {
  it("renders Resources heading", () => {
    renderWithQueryClient(<App />);
    const heading = screen.getByText(/^Resources$/i);
    expect(heading).toBeInTheDocument();
  });

  it("renders Resource heading", () => {
    renderWithQueryClient(<App />);
    const heading = screen.getByText(/^Resource \d+$/i);
    expect(heading).toBeInTheDocument();
  });

  it("renders both ResourcesView and ResourceView components", () => {
    renderWithQueryClient(<App />);

    // Check for ResourcesView content
    expect(screen.getByText(/^Resources$/i)).toBeInTheDocument();

    // Check for ResourceView content
    expect(screen.getByText(/^Resource \d+$/i)).toBeInTheDocument();
  });
});
