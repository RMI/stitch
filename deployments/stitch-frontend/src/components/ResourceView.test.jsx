import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithQueryClient } from "../test/utils";
import ResourceView from "./ResourceView";
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

describe("ResourceView", () => {
  it("stays disabled in interactive mode until Fetch/Enter is used", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(useResource).toHaveBeenLastCalledWith(
      "/api/v1/resources/{id}",
      1,
      false,
    );
  });

  it("auto-fetches in embedded mode (showControls=false with a known id)", () => {
    renderWithQueryClient(
      <ResourceView
        endpoint="/api/v1/resources/{id}"
        showControls={false}
        initialID={7}
      />,
    );

    expect(useResource).toHaveBeenLastCalledWith(
      "/api/v1/resources/{id}",
      7,
      true,
    );
  });

  it("renders heading with default ID and endpoint information", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(screen.getByText(/^Resource ID: \d+$/)).toBeInTheDocument();
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
    expect(screen.getByText(/^Resource ID: 42$/)).toBeInTheDocument();
  });

  it("calls refetch when Fetch button is clicked", async () => {
    const user = userEvent.setup();
    const mockRefetch = vi.fn();
    vi.mocked(useResource).mockReturnValue({
      ...defaultHookReturn,
      refetch: mockRefetch,
    });

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    await user.click(screen.getByRole("button", { name: /fetch/i }));

    expect(mockRefetch).toHaveBeenCalled();
  });

  it("calls refetch when Enter key is pressed in input", async () => {
    const user = userEvent.setup();
    const mockRefetch = vi.fn();
    vi.mocked(useResource).mockReturnValue({
      ...defaultHookReturn,
      refetch: mockRefetch,
    });

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "5{Enter}");

    expect(mockRefetch).toHaveBeenCalled();
  });

  it("displays structured data when resource is loaded", () => {
    const mockResource = {
      id: 1,
      name: "Test Resource",
      type: "example",
      status: "active",
    };
    vi.mocked(useResource).mockReturnValue({
      ...defaultHookReturn,
      data: mockResource,
    });

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(screen.getByText("ID")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Test Resource")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("example")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("displays error message when in error state", () => {
    vi.mocked(useResource).mockReturnValue({
      ...defaultHookReturn,
      isError: true,
      error: new Error("HTTP error! status: 404"),
    });

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(screen.getByText(/HTTP error! status: 404/)).toBeInTheDocument();
  });

  it("disables Clear Cache button when no data", () => {
    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(screen.getByRole("button", { name: /clear cache/i })).toBeDisabled();
  });

  it("enables Clear Cache button when data is loaded", () => {
    vi.mocked(useResource).mockReturnValue({
      ...defaultHookReturn,
      data: { id: 1, name: "Test Resource" },
    });

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).not.toBeDisabled();
  });

  it("enables Clear Cache button when in error state", () => {
    vi.mocked(useResource).mockReturnValue({
      ...defaultHookReturn,
      isError: true,
      error: new Error("HTTP error! status: 500"),
    });

    renderWithQueryClient(<ResourceView endpoint="/api/v1/resources/{id}" />);

    expect(
      screen.getByRole("button", { name: /clear cache/i }),
    ).not.toBeDisabled();
  });

  it("clears data when Clear Cache button is clicked", async () => {
    const user = userEvent.setup();
    vi.mocked(useResource).mockReturnValue({
      ...defaultHookReturn,
      data: { id: 1, name: "Test Resource" },
    });

    const { queryClient } = renderWithQueryClient(
      <ResourceView endpoint="/api/v1/resources/{id}" />,
    );
    // useResource is mocked, so nothing populates the cache on its own.
    // Seed the real cache entry under the "view" key (what useResource
    // actually uses) so this test can prove Clear Cache removes it, rather
    // than passing vacuously because nothing was ever there.
    const viewKey = ["/api/v1/resources/{id}", "view", 1];
    queryClient.setQueryData(viewKey, { id: 1, name: "Test Resource" });

    await user.click(screen.getByRole("button", { name: /clear cache/i }));

    // resetQueries clears cached data back to its initial (pending) state;
    // it doesn't deregister the query entirely, so assert on the data, not
    // on getQueryState being undefined.
    await waitFor(() => {
      expect(queryClient.getQueryData(viewKey)).toBeUndefined();
    });
  });
});
