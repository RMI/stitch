import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import EntityLinkagePage from "./EntityLinkagePage";
import * as jobsModule from "../queries/jobs";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";

const RUNNING_RECORD = {
  job_id: "job-123",
  state: "running",
  initiated_by: "Test User",
  params: { apply_merges: false, page: 1, page_size: 50, max_pages: null },
  started_at: "2026-01-01T00:00:00Z",
  finished_at: null,
  result: null,
  error: null,
};

const SUCCEEDED_RECORD = {
  ...RUNNING_RECORD,
  state: "succeeded",
  finished_at: "2026-01-01T00:00:05Z",
  result: {
    pages_fetched: 1,
    total_records_fetched: 4,
    duplicate_name_candidate_count: 4,
    detail_records_fetched: 4,
    match_groups: [
      [101, 102],
      [203, 204, 205],
    ],
    merge_results: [],
  },
};

describe("EntityLinkagePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
    // Default: no prior runs (loaded on mount).
    vi.spyOn(jobsModule, "listJobs").mockResolvedValue([]);
  });

  it("starts a run, auto-polls, and renders the completed result", async () => {
    const startSpy = vi
      .spyOn(jobsModule, "startJob")
      .mockResolvedValue(RUNNING_RECORD);
    vi.spyOn(jobsModule, "getJobStatus").mockResolvedValue(SUCCEEDED_RECORD);

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Match groups" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("2 groups")).toBeInTheDocument();
    expect(screen.getByText("Resource 101")).toBeInTheDocument();
    expect(screen.getByText("Resource 205")).toBeInTheDocument();

    // start body carries apply_merges + force; auto-poll happened (no manual refresh).
    expect(startSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ apply_merges: false, force: false }),
      expect.anything(),
    );
    expect(jobsModule.getJobStatus).toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: /refresh status/i }),
    ).not.toBeInTheDocument();
  });

  it("offers 'Show result' for a recent run and reveals it without re-running", async () => {
    vi.spyOn(jobsModule, "listJobs").mockResolvedValue([SUCCEEDED_RECORD]);
    const startSpy = vi.spyOn(jobsModule, "startJob");

    renderWithQueryClient(<EntityLinkagePage />);

    const showButton = await screen.findByRole("button", {
      name: /show result/i,
    });
    await userEvent.click(showButton);

    expect(
      await screen.findByRole("heading", { name: "Match groups" }),
    ).toBeInTheDocument();
    expect(startSpy).not.toHaveBeenCalled();
  });

  it("forces a re-run when Re-run is checked", async () => {
    const startSpy = vi
      .spyOn(jobsModule, "startJob")
      .mockResolvedValue(SUCCEEDED_RECORD);

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("checkbox", { name: /re-run/i }));
    await userEvent.click(screen.getByRole("button", { name: "Re-run" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Match groups" }),
      ).toBeInTheDocument();
    });
    expect(startSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ apply_merges: false, force: true }),
      expect.anything(),
    );
  });

  it("surfaces a failed run", async () => {
    vi.spyOn(jobsModule, "startJob").mockResolvedValue({
      ...RUNNING_RECORD,
      state: "failed",
      finished_at: "2026-01-01T00:00:05Z",
      error: "GET /oil-gas-fields/ failed with status 500: boom",
    });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(
        screen.getByText("GET /oil-gas-fields/ failed with status 500: boom"),
      ).toBeInTheDocument();
    });
  });
});
