import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  renderWithQueryClient,
  createMockResponse,
  createMockError,
} from "../test/utils";
import ResourcesView from "./ResourcesView";

describe("ResourcesView", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("renders heading and endpoint information", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByText("Resources")).toBeInTheDocument();
    expect(screen.getByText(/\/api\/v1\/resources\//)).toBeInTheDocument();
  });

  it("shows initial message before data is fetched", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByText(/No resources loaded/i)).toBeInTheDocument();
  });

  it("renders Fetch and Clear Cache buttons", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    expect(screen.getByRole("button", { name: /fetch/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).toBeInTheDocument();
  });

  it("disables Clear Cache button when no data", () => {
    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    const clearButton = screen.getByRole("button", { name: /clear cache/i });
    expect(clearButton).toBeDisabled();
  });

  it("fetches and displays resources when Fetch button is clicked", async () => {
    const user = userEvent.setup();
    const mockResources = [
      { id: 1, name: "Resource 1", type: "test" },
      { id: 2, name: "Resource 2", type: "test" },
    ];

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResources));

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText("Resource IDs")).toBeInTheDocument();
      // Check that both resource IDs are displayed
      const resourceIdsList =
        screen.getByText("Resource IDs").nextElementSibling;
      expect(resourceIdsList).toHaveTextContent("1");
      expect(resourceIdsList).toHaveTextContent("2");
    });
  });

  it("shows loading state while fetching", async () => {
    const user = userEvent.setup();
    global.fetch.mockImplementationOnce(
      () => new Promise((resolve) => setTimeout(resolve, 100)),
    );

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    expect(screen.getByRole("button", { name: /loading/i })).toBeInTheDocument();
  });

  it("displays error message when fetch fails", async () => {
    const user = userEvent.setup();
    global.fetch.mockResolvedValueOnce(createMockError(500));

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText("Error")).toBeInTheDocument();
      expect(screen.getByText(/HTTP error! status: 500/)).toBeInTheDocument();
    });
  });

  it("enables Clear Cache button after data is loaded", async () => {
    const user = userEvent.setup();
    const mockResources = [{ id: 1, name: "Resource 1" }];

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResources));

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      const clearButton = screen.getByRole("button", { name: /clear cache/i });
      expect(clearButton).not.toBeDisabled();
    });
  });

  it("clears cache when Clear Cache button is clicked", async () => {
    const user = userEvent.setup();
    const mockResources = [{ id: 1, name: "Resource 1" }];

    global.fetch.mockResolvedValueOnce(createMockResponse(mockResources));

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    // Fetch data first
    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText("Resource IDs")).toBeInTheDocument();
    });

    // Clear cache
    const clearButton = screen.getByRole("button", { name: /clear cache/i });
    await user.click(clearButton);

    await waitFor(() => {
      expect(screen.queryByText("Resource IDs")).not.toBeInTheDocument();
      expect(screen.getByText(/No resources loaded/i)).toBeInTheDocument();
    });
  });

  it("handles empty resources array", async () => {
    const user = userEvent.setup();
    global.fetch.mockResolvedValueOnce(createMockResponse([]));

    renderWithQueryClient(<ResourcesView endpoint="/api/v1/resources/" />);

    const fetchButton = screen.getByRole("button", { name: /fetch/i });
    await user.click(fetchButton);

    await waitFor(() => {
      expect(screen.getByText(/No resources loaded/i)).toBeInTheDocument();
    });
  });
});
