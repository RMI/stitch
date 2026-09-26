import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import EntityLinkagePage from "./EntityLinkagePage";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";

const START_URL = "http://localhost:8001/api/v1/oil-gas-fields/link";
const STATUS_URL = "http://localhost:8001/api/v1/oil-gas-fields/link/status";

const SUCCEEDED_RECORD = {
  job_id: "job-1",
  state: "succeeded",
  started_at: "2026-06-11T10:00:00Z",
  finished_at: "2026-06-11T10:05:00Z",
  error: null,
  result: {
    initiated_by: "Test User",
    apply_merges: false,
    resources_scanned: 5,
    match_groups: [
      [101, 102],
      [203, 204, 205],
    ],
    merge_candidates_created: 0,
    merge_candidates_skipped: 0,
  },
};

const RUNNING_WITH_PROGRESS_RECORD = {
  job_id: "job-1",
  state: "running",
  started_at: "2026-06-11T10:00:00Z",
  finished_at: null,
  error: null,
  result: null,
  progress: {
    resources_scanned: 120,
    total_resources: 1000,
    merge_candidates_created: 4,
    merge_candidates_skipped: 1,
    resources_failed: 0,
    updated_at: "2026-06-11T10:02:00Z",
  },
};

const RUNNING_NEAR_COMPLETE_RECORD = {
  ...RUNNING_WITH_PROGRESS_RECORD,
  progress: {
    ...RUNNING_WITH_PROGRESS_RECORD.progress,
    // 9951/10000 = 99.51%: rounds to 100 but must floor to 99 while running.
    resources_scanned: 9951,
    total_resources: 10000,
  },
};

const RUNNING_AT_TOTAL_RECORD = {
  ...RUNNING_WITH_PROGRESS_RECORD,
  progress: {
    ...RUNNING_WITH_PROGRESS_RECORD.progress,
    // Final 100-boundary of a run whose size is a multiple of 100: scanned == total
    // while still running. Stays determinate, clamped to 99% (not a false 100%).
    resources_scanned: 3000,
    total_resources: 3000,
  },
};

const RUNNING_OVER_TOTAL_RECORD = {
  ...RUNNING_WITH_PROGRESS_RECORD,
  progress: {
    ...RUNNING_WITH_PROGRESS_RECORD.progress,
    // Start-of-run total became stale as the dataset grew: scanned passed it.
    resources_scanned: 3050,
    total_resources: 3000,
  },
};

const RUNNING_WITHOUT_TOTAL_RECORD = {
  ...RUNNING_WITH_PROGRESS_RECORD,
  progress: {
    ...RUNNING_WITH_PROGRESS_RECORD.progress,
    resources_scanned: 120,
    total_resources: null,
  },
};

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  };
}

describe("EntityLinkagePage", () => {
  let getAccessTokenSilently;

  beforeEach(() => {
    getAccessTokenSilently = vi.fn().mockResolvedValue("test-access-token");
    vi.mocked(useAuth0).mockReturnValue({
      ...auth0TestDefaults,
      getAccessTokenSilently,
    });
  });

  it("launches a background run and shows the running state", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(202, {
        job_id: "job-1",
        state: "running",
        started_at: "2026-06-11T10:00:00Z",
        initiated_by: "Test User",
      }),
    );

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(screen.getAllByText("running").length).toBeGreaterThan(0);
    });

    expect(getAccessTokenSilently).toHaveBeenCalledWith({
      authorizationParams: { audience: "https://stitch-api.local" },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      START_URL,
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-access-token",
        }),
      }),
    );
  });

  it("defaults 'Initiate merges' on and posts apply_merges true", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(202, {
        job_id: "job-1",
        state: "running",
        started_at: "2026-06-11T10:00:00Z",
        initiated_by: "Test User",
      }),
    );

    renderWithQueryClient(<EntityLinkagePage />);

    expect(
      screen.getByRole("checkbox", { name: "Initiate merges" }),
    ).toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        START_URL,
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ apply_merges: true }),
        }),
      );
    });
  });

  it("renders match groups from the polled job result", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (url, options) => {
        if (String(url) === START_URL && options?.method === "POST") {
          return jsonResponse(202, {
            job_id: "job-1",
            state: "running",
            started_at: "2026-06-11T10:00:00Z",
            initiated_by: "Test User",
          });
        }
        return jsonResponse(200, SUCCEEDED_RECORD);
      });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Match groups" }),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("2 groups")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Match group 1" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Resource 101")).toBeInTheDocument();
    expect(screen.getByText("Resource 205")).toBeInTheDocument();

    // Status poll is authenticated (our /status is permission-gated).
    expect(fetchMock).toHaveBeenCalledWith(
      STATUS_URL,
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-access-token",
        }),
      }),
    );
  });

  it("renders a progress bar with counts while a run reports progress", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      if (String(url) === START_URL && options?.method === "POST") {
        return jsonResponse(202, {
          job_id: "job-1",
          state: "running",
          started_at: "2026-06-11T10:00:00Z",
          initiated_by: "Test User",
        });
      }
      return jsonResponse(200, RUNNING_WITH_PROGRESS_RECORD);
    });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(screen.getByText(/Processing/)).toBeInTheDocument();
    });

    // 120 of 1000 -> 12%.
    const bar = screen.getByRole("progressbar", {
      name: "Linkage run progress",
    });
    expect(bar).toHaveAttribute("aria-valuenow", "12");
    expect(screen.getByText("12%")).toBeInTheDocument();
    expect(screen.getByText(/4 candidates created/)).toBeInTheDocument();
    expect(screen.getByText(/Last updated/)).toBeInTheDocument();
  });

  it("does not reach 100% until the run is complete", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      if (String(url) === START_URL && options?.method === "POST") {
        return jsonResponse(202, {
          job_id: "job-1",
          state: "running",
          started_at: "2026-06-11T10:00:00Z",
          initiated_by: "Test User",
        });
      }
      return jsonResponse(200, RUNNING_NEAR_COMPLETE_RECORD);
    });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(screen.getByText(/Processing/)).toBeInTheDocument();
    });

    // 9951/10000 floors to 99, not 100, while still running.
    const bar = screen.getByRole("progressbar", {
      name: "Linkage run progress",
    });
    expect(bar).toHaveAttribute("aria-valuenow", "99");
    expect(screen.getByText("99%")).toBeInTheDocument();
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
  });

  it("stays determinate at 99% when scanned equals total (still running)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      if (String(url) === START_URL && options?.method === "POST") {
        return jsonResponse(202, {
          job_id: "job-1",
          state: "running",
          started_at: "2026-06-11T10:00:00Z",
          initiated_by: "Test User",
        });
      }
      return jsonResponse(200, RUNNING_AT_TOTAL_RECORD);
    });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(screen.getByText(/Processing 3,000 of 3,000/)).toBeInTheDocument();
    });

    // scanned == total while running: determinate, clamped to 99%, never 100%.
    const bar = screen.getByRole("progressbar", {
      name: "Linkage run progress",
    });
    expect(bar).toHaveAttribute("aria-valuenow", "99");
    expect(screen.getByText("99%")).toBeInTheDocument();
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
  });

  it("stays indeterminate when scanned passes a stale total (no stuck 100%)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      if (String(url) === START_URL && options?.method === "POST") {
        return jsonResponse(202, {
          job_id: "job-1",
          state: "running",
          started_at: "2026-06-11T10:00:00Z",
          initiated_by: "Test User",
        });
      }
      return jsonResponse(200, RUNNING_OVER_TOTAL_RECORD);
    });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(screen.getByText(/Processing 3,050/)).toBeInTheDocument();
    });

    // scanned > total: no percent, no aria-valuenow, and no misleading "of".
    const bar = screen.getByRole("progressbar", {
      name: "Linkage run progress",
    });
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/of 3,000/)).not.toBeInTheDocument();
  });

  it("renders an indeterminate bar when the total is unknown", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      if (String(url) === START_URL && options?.method === "POST") {
        return jsonResponse(202, {
          job_id: "job-1",
          state: "running",
          started_at: "2026-06-11T10:00:00Z",
          initiated_by: "Test User",
        });
      }
      return jsonResponse(200, RUNNING_WITHOUT_TOTAL_RECORD);
    });

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh status" }),
    );

    await waitFor(() => {
      expect(screen.getByText(/Processing 120/)).toBeInTheDocument();
    });

    // Unknown total -> no percent and no aria-valuenow (indeterminate bar).
    const bar = screen.getByRole("progressbar", {
      name: "Linkage run progress",
    });
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("surfaces a friendly message when a run is already in progress (409)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(409, { detail: "A job is already running: job-1" }),
    );

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "A run is already in progress — refresh status to check.",
        ),
      ).toBeInTheDocument();
    });
  });
});
