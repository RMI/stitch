import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useIsFetching } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setConfigForTests } from "../config/env";
import { renderWithQueryClient } from "../test/utils";

function createMockConfig() {
  return {
    appEnv: "local",
    apiBaseUrl: "http://localhost:8000/api/v1",
    entityLinkageBaseUrl: "http://localhost:8001/api/v1",
    auth0: {
      domain: "example.auth0.com",
      clientId: "client-id",
      audience: "https://stitch-api.local",
    },
    build: {
      appVersion: "0.0.0",
      buildId: "local-build",
      gitSha: "abcdef123456",
      nodeVersion: "v20.0.0",
      viteVersion: "^7.2.4",
      buildTime: "2026-04-06T12:00:00Z",
    },
  };
}

vi.mock("./ColophonPanel", () => ({
  default: ({ diagnosticsOpen }) => (
    <div data-testid="colophon-panel">
      Diagnostics open: {String(diagnosticsOpen)}
    </div>
  ),
}));

// Only `useIsFetching` is faked; the real QueryClient/Provider are still needed
// by renderWithQueryClient.
vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal()),
  useIsFetching: vi.fn(() => 0),
}));

describe("EnvironmentBanner", () => {
  let mockConfig;

  beforeEach(() => {
    mockConfig = createMockConfig();
    setConfigForTests(mockConfig);
  });

  it("renders for a non-production environment", async () => {
    const { default: EnvironmentBanner } = await import("./EnvironmentBanner");

    renderWithQueryClient(<EnvironmentBanner />);

    expect(screen.getByText("LOCAL Environment")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Show diagnostics" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("colophon-panel")).not.toBeInTheDocument();
  });

  it("hides entirely for production", async () => {
    setConfigForTests({
      ...createMockConfig(),
      appEnv: "production",
    });
    const { default: EnvironmentBanner } = await import("./EnvironmentBanner");

    const { container } = renderWithQueryClient(<EnvironmentBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it("toggles the diagnostics panel open and closed", async () => {
    const user = userEvent.setup();
    const { default: EnvironmentBanner } = await import("./EnvironmentBanner");

    renderWithQueryClient(<EnvironmentBanner />);

    const toggle = screen.getByRole("button", { name: "Show diagnostics" });

    await user.click(toggle);
    expect(
      screen.getByRole("button", { name: "Hide diagnostics" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("colophon-panel")).toHaveTextContent(
      "Diagnostics open: true",
    );

    await user.click(screen.getByRole("button", { name: "Hide diagnostics" }));
    expect(
      screen.getByRole("button", { name: "Show diagnostics" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("colophon-panel")).not.toBeInTheDocument();
  });

  describe("waking-up notice", () => {
    const WAKING_TEXT = /waking up/i;

    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    async function renderBanner() {
      const { default: EnvironmentBanner } =
        await import("./EnvironmentBanner");
      return renderWithQueryClient(<EnvironmentBanner />);
    }

    it("stays quiet while nothing is pending, however long the page is open", async () => {
      vi.mocked(useIsFetching).mockReturnValue(0);
      await renderBanner();

      act(() => vi.advanceTimersByTime(60_000));

      expect(screen.queryByText(WAKING_TEXT)).not.toBeInTheDocument();
    });

    it("stays quiet for a request that is merely in flight", async () => {
      vi.mocked(useIsFetching).mockReturnValue(1);
      await renderBanner();

      // A healthy request resolves well inside the delay, so the user should
      // never see this for a normal page load.
      act(() => vi.advanceTimersByTime(1_500));

      expect(screen.queryByText(WAKING_TEXT)).not.toBeInTheDocument();
    });

    it("explains the wait once a request has stalled", async () => {
      vi.mocked(useIsFetching).mockReturnValue(1);
      await renderBanner();

      act(() => vi.advanceTimersByTime(2_000));

      expect(screen.getByRole("status")).toHaveTextContent(WAKING_TEXT);
    });

    it("stays silent once the server has answered something, however slow a later request is", async () => {
      vi.mocked(useIsFetching).mockReturnValue(1);
      const { queryClient } = await renderBanner();

      // A successful query proves the container is serving, so a later stall is
      // slow for some other reason and must not be blamed on a cold start.
      queryClient.setQueryData(["already-loaded"], { ok: true });

      // useIsFetching is mocked, so the cache write does not re-render on its
      // own; the toggle is just a cheap way to force one.
      fireEvent.click(screen.getByRole("button", { name: "Show diagnostics" }));
      act(() => vi.advanceTimersByTime(10_000));

      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("clears the notice once the request lands", async () => {
      vi.mocked(useIsFetching).mockReturnValue(1);
      await renderBanner();

      act(() => vi.advanceTimersByTime(2_000));
      expect(screen.getByRole("status")).toBeInTheDocument();

      // Fetching stops; the click is just a cheap way to force a re-render.
      vi.mocked(useIsFetching).mockReturnValue(0);
      fireEvent.click(screen.getByRole("button", { name: "Show diagnostics" }));

      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
