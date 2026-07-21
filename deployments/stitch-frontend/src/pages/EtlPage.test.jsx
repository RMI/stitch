import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import EtlPage from "./EtlPage";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";

function getPanel(title) {
  return screen.getByRole("heading", { name: title }).closest("section");
}

describe("EtlPage", () => {
  let getAccessTokenSilently;

  beforeEach(() => {
    getAccessTokenSilently = vi.fn().mockResolvedValue("test-access-token");
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      getAccessTokenSilently,
    });
  });

  it("renders a panel for each ETL pipeline", () => {
    renderWithQueryClient(<EtlPage />);

    expect(screen.getByRole("heading", { name: "GEM" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "WoodMac" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Start run" })).toHaveLength(
      2,
    );
    expect(
      screen.getAllByRole("button", { name: "Refresh status" }),
    ).toHaveLength(2);
  });

  it("starts a GEM run with an authenticated token and shows the returned state", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 202,
      text: async () =>
        JSON.stringify({
          job_id: "job-123",
          state: "running",
          started_at: "2026-06-11T10:00:00Z",
          initiated_by: "Test User",
        }),
    });

    renderWithQueryClient(<EtlPage />);

    const gemPanel = getPanel("GEM");
    await userEvent.click(
      within(gemPanel).getByRole("button", { name: "Start run" }),
    );

    await waitFor(() => {
      expect(within(gemPanel).getAllByText("running").length).toBeGreaterThan(
        0,
      );
    });

    expect(getAccessTokenSilently).toHaveBeenCalledWith({
      authorizationParams: { audience: "https://stitch-api.local" },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8100/api/v1/etl/gem/start",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-access-token",
        }),
      }),
    );
  });

  it("surfaces a friendly message when a run is already in progress (409)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({ detail: "A run is already active" }),
    });

    renderWithQueryClient(<EtlPage />);

    const woodmacPanel = getPanel("WoodMac");
    await userEvent.click(
      within(woodmacPanel).getByRole("button", { name: "Start run" }),
    );

    await waitFor(() => {
      expect(
        within(woodmacPanel).getByText(
          "A run is already in progress — refresh status to check.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("refreshes status via an unauthenticated GET", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          job_id: "job-789",
          state: "succeeded",
          started_at: "2026-06-11T10:00:00Z",
          finished_at: "2026-06-11T10:05:00Z",
          result: { payloads_posted: 42 },
        }),
    });

    renderWithQueryClient(<EtlPage />);

    const woodmacPanel = getPanel("WoodMac");
    await userEvent.click(
      within(woodmacPanel).getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(
        within(woodmacPanel).getAllByText("succeeded").length,
      ).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8100/api/v1/etl/wm/status",
    );
  });
});
