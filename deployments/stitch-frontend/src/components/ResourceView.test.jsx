import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  renderWithQueryClient,
  createMockResponse,
  createMockError,
} from "../test/utils";
import ResourceView from "./ResourceView";

describe("ResourceView", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("renders heading with default ID and endpoint information", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(screen.getByText(/^Resource \d+$/)).toBeInTheDocument();
    expect(screen.getByText(/\/api\/v1\/resources\//)).toBeInTheDocument();
  });

  it("renders input field with default value of 1", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const input = screen.getByRole("spinbutton");
    expect(input).toHaveValue(1);
  });

  it("renders Fetch and Clear Cache buttons", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(screen.getByRole("button", { name: /fetch/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).toBeInTheDocument();
  });

  it("shows initial message before data is fetched", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(screen.getByText(/No resource loaded/i)).toBeInTheDocument();
  });

  it("allows changing the resource ID in the input", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "42");

    expect(input).toHaveValue(42);
    expect(screen.getByText(/^Resource 42$/)).toBeInTheDocument();
  });

  it("fetches resource when Fetch button is clicked", async () => {
    const user = userEvent.setup();
    const mockResource = { id: 1, name: "Test Resource", type: "test" };

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResource));

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText(/Test Resource/)).toBeInTheDocument();
    });
  });

  it("fetches resource when Enter key is pressed in input", async () => {
    const user = userEvent.setup();
    const mockResource = { id: 5, name: "Resource 5", type: "test" };

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResource));

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "5{Enter}");

    await waitFor(() => {
      expect(screen.getByText(/"name": "Resource 5"/)).toBeInTheDocument();
    });
  });

  it("displays JSON data for successful fetch", async () => {
    const user = userEvent.setup();
    const mockResource = {
      id: 1,
      name: "Test Resource",
      type: "example",
      status: "active",
    };

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResource));

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText(/"id": 1/)).toBeInTheDocument();
      expect(screen.getByText(/"name": "Test Resource"/)).toBeInTheDocument();
      expect(screen.getByText(/"type": "example"/)).toBeInTheDocument();
      expect(screen.getByText(/"status": "active"/)).toBeInTheDocument();
    });
  });

  it("displays error message when fetch fails", async () => {
    const user = userEvent.setup();
    global.fetch.mockResolvedValueOnce(createMockError(404));

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText("Not Found")).toBeInTheDocument();
    });
  });

  it("disables Clear Cache button when no data", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const clearButton = screen.getByRole("button", { name: /clear cache/i });
    expect(clearButton).toBeDisabled();
  });

  it("enables Clear Cache button after data is loaded", async () => {
    const user = userEvent.setup();
    const mockResource = { id: 1, name: "Test Resource" };

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResource));

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      const clearButton = screen.getByRole("button", { name: /clear cache/i });
      expect(clearButton).not.toBeDisabled();
    });
  });

  it("enables Clear Cache button after error", async () => {
    const user = userEvent.setup();
    global.fetch.mockResolvedValueOnce(createMockError(500));

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      const clearButton = screen.getByRole("button", { name: /clear cache/i });
      expect(clearButton).not.toBeDisabled();
    });
  });

  it("clears cache when Clear Cache button is clicked", async () => {
    const user = userEvent.setup();
    const mockResource = { id: 1, name: "Test Resource" };

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResource));

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    // Fetch data first
    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText(/Test Resource/)).toBeInTheDocument();
    });

    // Clear cache
    const clearButton = screen.getByRole("button", { name: /clear cache/i });
    await user.click(clearButton);

    await waitFor(() => {
      expect(screen.queryByText(/Test Resource/)).not.toBeInTheDocument();
      expect(screen.getByText(/No resource loaded/i)).toBeInTheDocument();
    });
  });
});
