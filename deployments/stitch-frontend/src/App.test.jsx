import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App", () => {
  it("renders hello world heading", () => {
    render(<App />);
    const heading = screen.getByText(/hello world/i);
    expect(heading).toBeInTheDocument();
  });

  it("heading has correct styling classes", () => {
    render(<App />);
    const heading = screen.getByText(/hello world/i);
    expect(heading).toHaveClass("text-3xl", "font-bold", "underline");
  });
});
