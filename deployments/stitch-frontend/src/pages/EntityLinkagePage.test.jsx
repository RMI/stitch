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
