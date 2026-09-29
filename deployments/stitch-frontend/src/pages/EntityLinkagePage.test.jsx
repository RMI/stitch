import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth0 } from "@auth0/auth0-react";
import EntityLinkagePage from "./EntityLinkagePage";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";

const LINK_ALL_URL =
  "http://localhost:8000/api/v1/oil-gas-fields/merge-candidates/link-all";

const LINK_ALL_RESPONSE = {
  apply_merges: false,
  match_groups: [
    [101, 102],
    [203, 204, 205],
  ],
  merge_candidates_created: 0,
  merge_candidates_skipped: 0,
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

  it("posts an authenticated dry run to the API", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(200, LINK_ALL_RESPONSE));

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    expect(getAccessTokenSilently).toHaveBeenCalledWith({
      authorizationParams: { audience: "https://stitch-api.local" },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      `${LINK_ALL_URL}?apply_merges=false`,
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-access-token",
        }),
      }),
    );
  });

  // apply_merges is a query parameter, so a body would be silently ignored and
  // every run would quietly be a dry run.
  it("sends apply_merges as a query parameter when the box is checked", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(200, LINK_ALL_RESPONSE));

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByLabelText("Initiate merges"));
    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      `${LINK_ALL_URL}?apply_merges=true`,
    );
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("body");
  });

  it("renders match groups from the response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(200, LINK_ALL_RESPONSE),
    );

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

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
  });

  it("surfaces the status code when the request is rejected", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(403, {
        detail: "Missing permission: merge-candidate:create",
      }),
    );

    renderWithQueryClient(<EntityLinkagePage />);

    await userEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Run error" }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Missing permission: merge-candidate:create/),
    ).toBeInTheDocument();
  });
});
