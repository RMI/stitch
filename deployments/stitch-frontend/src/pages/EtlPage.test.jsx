import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import EtlPage from "./EtlPage";
import * as jobsModule from "../queries/jobs";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";

const GEM_BASE = "http://localhost:8101/api/v1";

function getPanel(title) {
  return screen.getByRole("heading", { name: title }).closest("section");
}

function succeededRecord(overrides = {}) {
  return {
    job_id: "job-123",
    state: "succeeded",
    started_at: "2026-06-11T10:00:00Z",
    finished_at: "2026-06-11T10:05:00Z",
    params: {},
    result: { payloads_posted: 42 },
    error: null,
    ...overrides,
  };
}

describe("EtlPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
    vi.spyOn(jobsModule, "listJobs").mockResolvedValue([]);
  });

  it("renders a panel for each ETL pipeline with no manual refresh", () => {
    renderWithQueryClient(<EtlPage />);

    expect(screen.getByRole("heading", { name: "GEM" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "WoodMac" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Start run" })).toHaveLength(
      2,
    );
    expect(
      screen.queryByRole("button", { name: /refresh status/i }),
    ).not.toBeInTheDocument();
  });

  it("starts a GEM run and renders the completed result", async () => {
    const startSpy = vi
      .spyOn(jobsModule, "startJob")
      .mockResolvedValue(succeededRecord());

    renderWithQueryClient(<EtlPage />);

    const gemPanel = getPanel("GEM");
    await userEvent.click(
      within(gemPanel).getByRole("button", { name: "Start run" }),
    );

    await waitFor(() => {
      expect(within(gemPanel).getByText("succeeded")).toBeInTheDocument();
    });

    expect(startSpy).toHaveBeenCalledWith(
      GEM_BASE,
      expect.objectContaining({ force: false }),
      expect.anything(),
    );
  });

  it("offers 'Show result' for a recent run and reveals it without re-running", async () => {
    vi.spyOn(jobsModule, "listJobs").mockImplementation(async (baseUrl) =>
      baseUrl === GEM_BASE ? [succeededRecord()] : [],
    );
    const startSpy = vi.spyOn(jobsModule, "startJob");

    renderWithQueryClient(<EtlPage />);

    const gemPanel = getPanel("GEM");
    const showButton = await within(gemPanel).findByRole("button", {
      name: /show result/i,
    });
    await userEvent.click(showButton);

    await waitFor(() => {
      expect(within(gemPanel).getByText("succeeded")).toBeInTheDocument();
    });
    expect(startSpy).not.toHaveBeenCalled();
  });

  it("forces a re-run when Re-run is checked", async () => {
    const startSpy = vi
      .spyOn(jobsModule, "startJob")
      .mockResolvedValue(succeededRecord());

    renderWithQueryClient(<EtlPage />);

    const gemPanel = getPanel("GEM");
    await userEvent.click(
      within(gemPanel).getByRole("checkbox", { name: /re-run/i }),
    );
    await userEvent.click(
      within(gemPanel).getByRole("button", { name: "Re-run" }),
    );

    await waitFor(() => {
      expect(within(gemPanel).getByText("succeeded")).toBeInTheDocument();
    });
    expect(startSpy).toHaveBeenCalledWith(
      GEM_BASE,
      expect.objectContaining({ force: true }),
      expect.anything(),
    );
  });
});
