import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAuth0 } from "@auth0/auth0-react";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import ResourceDetailPage from "./ResourceDetailPage";
import {
  useResourceDetail,
  useSourceDetail,
  useFieldSourceValues,
} from "../hooks/useResources";
import { usePermissions } from "../hooks/usePermissions";
import * as apiModule from "../queries/api";
import { AI_SUGGESTION_FIELDS } from "../constants/fieldMeta";

// Mock only the read hooks; the attach path exercises the real
// useCreateSourceForResource mutation against a spied API module.
vi.mock("../hooks/useResources", async (importOriginal) => ({
  ...(await importOriginal()),
  useResourceDetail: vi.fn(),
  useSourceDetail: vi.fn(),
  useFieldSourceValues: vi.fn(),
}));
vi.mock("../hooks/usePermissions");

let mockedRouteId = "1";
const mockNavigate = vi.fn();

vi.mock("react-router", async () => {
  const actual = await vi.importActual("react-router");
  return {
    ...actual,
    useParams: () => ({ id: mockedRouteId }),
    useNavigate: () => mockNavigate,
  };
});

const mockDetailView = {
  id: 1,
  data: {
    name: "Burgan Field",
    country: "Kuwait",
    state_province: "Kuwait",
    region: "Middle East",
    basin: "Arabian",
    latitude: 29.05,
    longitude: 47.95,
    location_type: "Onshore",
    name_local: null,
    owners: [
      { name: "Kuwait Oil Company", stake: 100 },
      // Providers often name a party without stating a percentage.
      { name: "Kuwait Petroleum Corporation", stake: null },
    ],
    operators: [{ name: "Kuwait Oil Company", stake: null }],
    field_status: "Producing",
    production_conventionality: "Conventional",
    primary_hydrocarbon_group: "Oil",
    reservoir_formation: "Burgan",
    discovery_year: 1938,
    production_start_year: 1946,
    fid_year: null,
  },
  provenance: {},
  source_data: [
    {
      id: 11,
      source: "gem",
      name: "Burgan Source",
      country: "Kuwait",
    },
  ],
};

const defaultSourceDetailHookReturn = {
  data: null,
  isLoading: false,
  isError: false,
  error: null,
};

const defaultHookReturn = {
  data: null,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  mockedRouteId = "1";
  mockNavigate.mockReset();
  vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
  vi.mocked(useResourceDetail).mockReturnValue({
    ...defaultHookReturn,
    refetch: vi.fn(),
  });
  vi.mocked(useSourceDetail).mockReturnValue(defaultSourceDetailHookReturn);
  vi.mocked(useFieldSourceValues).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  // Default: permissions resolved, caller has every permission the panel checks.
  vi.mocked(usePermissions).mockReturnValue({
    data: ["service:llm:suggest", "source:write", "resource:write"],
    isLoading: false,
  });
  vi.stubGlobal("crypto", {
    randomUUID: () => "persist-uuid-123",
  });
});

describe("ResourceDetailPage", () => {
  it("shows an invalid ID message for a non-numeric route param", () => {
    mockedRouteId = "not-a-number";

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getByText(/invalid resource id/i)).toBeInTheDocument();
  });

  it("shows a loading indicator while fetching", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      isLoading: true,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an error message on fetch failure", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      isError: true,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getByText(/failed to load resource/i)).toBeInTheDocument();
  });

  it("renders the resource name as the page heading", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: "Burgan Field", level: 1 }),
    ).toBeInTheDocument();
  });

  it("renders the Identity and Location section header", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /identity and location/i }),
    ).toBeInTheDocument();
  });

  it("renders identity fields with their values", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getAllByText("Country").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Kuwait").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Region").length).toBeGreaterThan(0);
    expect(screen.getByText("Middle East")).toBeInTheDocument();
  });

  it("renders an em dash for null identity fields", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getAllByText("Local Name").length).toBeGreaterThan(0);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("renders the Organizations section header", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /organizations/i }),
    ).toBeInTheDocument();
  });

  it("renders owner and operator names", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getAllByText("Kuwait Oil Company").length).toBeGreaterThan(0);
  });

  it("renders a stated stake but leaves an unstated stake blank", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getAllByText("Kuwait Petroleum Corporation").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.queryByText("null%")).not.toBeInTheDocument();
  });

  it("renders the Production and Geology section header", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /production and geology/i }),
    ).toBeInTheDocument();
  });

  it("renders production fields with their values", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(screen.getAllByText("Field Status").length).toBeGreaterThan(0);
    expect(screen.getByText("Producing")).toBeInTheDocument();
    expect(screen.getAllByText("Discovery Year").length).toBeGreaterThan(0);
    expect(screen.getByText("1938")).toBeInTheDocument();
  });

  it("renders the Data Source Mix section", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);
    expect(
      screen.getByRole("heading", { name: /data source mix/i }),
    ).toBeInTheDocument();
  });

  it("renders the AI Suggestion section", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.getByRole("heading", { name: /ai suggestion/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /generate suggestion/i }),
    ).toBeInTheDocument();
  });

  it("renders a Sources section with a row per attached source", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.getByRole("heading", { name: /^sources$/i, level: 2 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^view$/i })).toBeInTheDocument();
    expect(screen.getAllByText("Burgan Source").length).toBeGreaterThan(0);
  });

  it("exposes disclosure accessibility attributes on the source row toggle", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);

    const toggle = screen.getByRole("button", { name: /^view$/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const panelId = toggle.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();

    await user.click(toggle);

    expect(screen.getByRole("button", { name: /^hide$/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(document.getElementById(panelId)).toBeTruthy();
  });

  it("shows formatted producer and observed-at in the compact row once the source detail loads", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.mocked(useSourceDetail).mockReturnValue({
      ...defaultSourceDetailHookReturn,
      data: {
        id: 11,
        source: "gem",
        name: "Burgan Source",
        source_record: {
          producer: "stitch-seed@0.1.0",
          observed_at: "2026-05-13T12:00:00Z",
          record_id: "abc",
          run_id: "run-1",
          payload: { name: "Burgan Source" },
        },
      },
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.getByText(/imported by stitch-seed@0\.1\.0/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/may 13, 2026/i)).toBeInTheDocument();
    expect(screen.queryByText(/"name": "Burgan Source"/)).toBeNull();
  });

  it("reveals the raw payload only after the Technical import record disclosure is opened", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.mocked(useSourceDetail).mockReturnValue({
      ...defaultSourceDetailHookReturn,
      data: {
        id: 11,
        source: "gem",
        name: "Burgan Source",
        source_record: {
          producer: "stitch-seed@0.1.0",
          observed_at: "2026-05-13T12:00:00Z",
          record_id: "abc",
          run_id: "run-1",
          payload: { name: "Burgan Source" },
        },
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(screen.getByRole("button", { name: /^view$/i }));

    const techToggle = screen.getByRole("button", {
      name: /technical import record/i,
    });
    expect(techToggle).toBeInTheDocument();
    expect(screen.queryByText(/"name": "Burgan Source"/)).toBeNull();

    await user.click(techToggle);

    expect(screen.getByText(/"name": "Burgan Source"/)).toBeInTheDocument();
    expect(screen.getByText("abc")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
  });

  it("shows the curator note from the source payload in the source details", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.mocked(useSourceDetail).mockReturnValue({
      ...defaultSourceDetailHookReturn,
      data: {
        id: 11,
        source: "rmi",
        name: "Burgan Source",
        source_record: {
          producer: "stitch-frontend",
          observed_at: "2026-05-13T12:00:00Z",
          record_id: null,
          run_id: null,
          payload: {
            action: "field_overwrite",
            field: "basin",
            value: "Arabian",
            note: "Confirmed with the survey team.",
          },
        },
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(screen.getByRole("button", { name: /^view$/i }));

    expect(screen.getByText("Note")).toBeInTheDocument();
    expect(
      screen.getByText("Confirmed with the survey team."),
    ).toBeInTheDocument();
  });

  it("omits the Note block when the source payload has no note", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.mocked(useSourceDetail).mockReturnValue({
      ...defaultSourceDetailHookReturn,
      data: {
        id: 11,
        source: "gem",
        name: "Burgan Source",
        source_record: {
          producer: "stitch-seed@0.1.0",
          observed_at: "2026-05-13T12:00:00Z",
          record_id: "abc",
          run_id: "run-1",
          payload: { name: "Burgan Source" },
        },
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(screen.getByRole("button", { name: /^view$/i }));

    expect(screen.queryByText("Note")).not.toBeInTheDocument();
  });

  it("generates and renders an AI suggestion preview", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [
        {
          url: "https://example.com/daqing",
          title: "Daqing citation",
        },
      ],
      query_succeeded: true,
      model: "test-model",
      rationale: "Public sources place Daqing in the Songliao Basin.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(await screen.findByText("Songliao")).toBeInTheDocument();
    expect(
      screen.getByText("Public sources place Daqing in the Songliao Basin."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Daqing citation" }),
    ).toHaveAttribute("href", "https://example.com/daqing");
  });

  it("renders a no-answer suggestion state without treating it as an error", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: null,
      citations: [],
      query_succeeded: true,
      model: "test-model",
      rationale: "I could not find a grounded public source for this field.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(
      await screen.findByText(/no grounded suggestion was returned/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "I could not find a grounded public source for this field.",
      ),
    ).toBeInTheDocument();
  });

  it("renders Add to resource only when the suggestion has a value", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [],
      query_succeeded: true,
      model: "test-model",
      rationale: "Supported.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(
      await screen.findByRole("button", { name: /add to resource/i }),
    ).toBeInTheDocument();
  });

  it("enables the detail query only for a valid id, so invalidations refetch it", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    const { unmount } = renderWithQueryClient(<ResourceDetailPage />);
    expect(useResourceDetail).toHaveBeenCalledWith("oil-gas-fields", 1, true);
    // Unmount before re-rendering: mockedRouteId is a shared module variable
    // read fresh by the mocked useParams() on every render, so a still-mounted
    // first instance would pick up the new value on any later re-render and
    // could call useResourceDetail again — racing the second instance's call
    // and making toHaveBeenLastCalledWith flaky. (rerender() isn't an option
    // here: renderWithQueryClient inlines its providers into one render()
    // call rather than using RTL's `wrapper` option, so rerender() would
    // replace the whole wrapped tree with an unwrapped one.)
    unmount();

    mockedRouteId = "not-a-number";
    renderWithQueryClient(<ResourceDetailPage />);
    expect(useResourceDetail).toHaveBeenLastCalledWith(
      "oil-gas-fields",
      NaN,
      false,
    );
  });

  it("creates an llm source and attaches it to the resource, staying on the page", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [
        { url: "https://example.com/source", title: "Example Source" },
      ],
      query_succeeded: true,
      model: "test-model",
      rationale: "Supported.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: { request: true },
      foundry_response: { response: true },
    });
    const createSourceSpy = vi
      .spyOn(apiModule, "createSourceForResource")
      .mockResolvedValue({ id: 123, source: "llm" });
    const user = userEvent.setup();

    const { queryClient } = renderWithQueryClient(<ResourceDetailPage />);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(createSourceSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBaseUrl: "http://localhost:8000/api/v1",
        stitchLlmBaseUrl: "http://localhost:8002/api/v1",
      }),
      1,
      {
        source: "llm",
        name: null,
        country: null,
        basin: "Songliao",
        source_record: {
          record_id: "persist-uuid-123",
          run_id: null,
          observed_at: "2026-05-13T12:00:00Z",
          producer: "stitch-frontend",
          payload: {
            resource_id: 1,
            field: "basin",
            suggested_value: "Songliao",
            rationale: "Supported.",
            citations: [
              {
                url: "https://example.com/source",
                title: "Example Source",
              },
            ],
            model: "test-model",
            foundry_request: { request: true },
            foundry_response: { response: true },
            persist_intent_id: "persist-uuid-123",
          },
        },
      },
      expect.any(Function),
      "oil-gas-fields",
    );
    expect(
      await screen.findByText("Source added to resource."),
    ).toBeInTheDocument();
    // The attach changes the resource's coalesced data, so everything cached
    // under the endpoint refreshes.
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["oil-gas-fields"],
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("renders structured create-source validation errors instead of object coercions", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [],
      query_succeeded: true,
      model: "test-model",
      rationale: "Supported.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    vi.spyOn(apiModule, "createSourceForResource").mockRejectedValue(
      new Error(
        JSON.stringify(
          [
            {
              loc: ["body", "llm", "name"],
              msg: "Field required",
            },
            {
              loc: ["body", "llm", "country"],
              msg: "Field required",
            },
          ],
          null,
          2,
        ),
      ),
    );
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(await screen.findByText(/Field required/)).toBeInTheDocument();
    expect(
      screen.queryByText("[object Object],[object Object]"),
    ).not.toBeInTheDocument();
  });

  it("surfaces the API error when attaching the source fails", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [],
      query_succeeded: true,
      model: "test-model",
      rationale: "Supported.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    vi.spyOn(apiModule, "createSourceForResource").mockRejectedValue(
      new Error("attach failed"),
    );
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(await screen.findByText("attach failed")).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("holds a placeholder (no controls) while permissions are still loading", () => {
    // Still loading: no permission data yet, so the placeholder wins.
    vi.mocked(usePermissions).mockReturnValue({ isLoading: true });
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(screen.getByTestId("ai-suggestion-loading")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /generate suggestion/i }),
    ).not.toBeInTheDocument();
  });

  it("hides the entire AI Suggestion panel when the user cannot run LLM suggestions", async () => {
    // No service:llm:suggest -> the whole panel is gone (even with write perms).
    vi.mocked(usePermissions).mockReturnValue({
      data: ["source:write", "resource:write"],
      isLoading: false,
    });
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.queryByRole("heading", { name: /ai suggestion/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /generate suggestion/i }),
    ).not.toBeInTheDocument();
  });

  it("hides the add-to-resource action when the user lacks write permissions", async () => {
    // Can run LLM (panel shows) but has neither write permission.
    vi.mocked(usePermissions).mockReturnValue({
      data: ["service:llm:suggest"],
      isLoading: false,
    });
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const createSourceSpy = vi.spyOn(apiModule, "createSourceForResource");
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [],
      query_succeeded: true,
      model: "test-model",
      rationale: "Supported.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    // Suggestion still renders, but the write-gated action is not offered.
    expect(await screen.findByText("Songliao")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /add to resource/i }),
    ).not.toBeInTheDocument();
    expect(createSourceSpy).not.toHaveBeenCalled();
  });

  it("hides the add-to-resource action when the user has only one of the two write permissions", async () => {
    // Can run LLM + source:write granted, but resource:write missing -> action
    // stays hidden (attach needs both).
    vi.mocked(usePermissions).mockReturnValue({
      data: ["service:llm:suggest", "source:write"],
      isLoading: false,
    });
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const createSourceSpy = vi.spyOn(apiModule, "createSourceForResource");
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [],
      query_succeeded: true,
      model: "test-model",
      rationale: "Supported.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );

    expect(await screen.findByText("Songliao")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /add to resource/i }),
    ).not.toBeInTheDocument();
    expect(createSourceSpy).not.toHaveBeenCalled();
  });

  it("disables resubmission after a successful attach for the current suggestion", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockResolvedValue({
      resource_id: 1,
      field: "basin",
      value: "Songliao",
      citations: [],
      query_succeeded: true,
      model: "test-model",
      rationale: "Supported.",
      observed_at: "2026-05-13T12:00:00Z",
      foundry_request: {},
      foundry_response: {},
    });
    vi.spyOn(apiModule, "createSourceForResource").mockResolvedValue({
      id: 123,
      source: "llm",
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /generate suggestion/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /add to resource/i }),
    );

    expect(
      await screen.findByRole("button", { name: /added to resource/i }),
    ).toBeDisabled();
  });

  it("fans out an AbortSignal-scoped request to every AI suggestion field on Enrich", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const suggestionSpy = vi
      .spyOn(apiModule, "createLLMSuggestion")
      .mockImplementation(async (_config, _id, field) => ({
        resource_id: 1,
        field,
        value: `value-${field}`,
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      }));
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /enrich this resource/i }),
    );

    await screen.findByText("value-name");
    expect(suggestionSpy).toHaveBeenCalledTimes(AI_SUGGESTION_FIELDS.length);
    for (const field of AI_SUGGESTION_FIELDS) {
      expect(suggestionSpy).toHaveBeenCalledWith(
        expect.anything(),
        1,
        field,
        expect.any(Function),
        "oil-gas-fields",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    }
  });

  it("renders per-field results as each Enrich request resolves", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const deferreds = {};
    vi.spyOn(apiModule, "createLLMSuggestion").mockImplementation(
      (_config, _id, field) =>
        new Promise((resolve) => {
          deferreds[field] = resolve;
        }),
    );
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /enrich this resource/i }),
    );

    // With every request pending, every field's card shows a generating hint.
    await waitFor(() =>
      expect(screen.getAllByText(/generating suggestion…/i).length).toBe(
        AI_SUGGESTION_FIELDS.length,
      ),
    );

    // Resolve just one field; its card renders while the rest still say
    // "Generating…", proving results stream in independently.
    await act(async () => {
      deferreds.name({
        resource_id: 1,
        field: "name",
        value: "Burgan A",
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      });
    });
    expect(await screen.findByText("Burgan A")).toBeInTheDocument();
    expect(screen.getAllByText(/generating suggestion…/i).length).toBe(
      AI_SUGGESTION_FIELDS.length - 1,
    );
  });

  it("keeps Enrich disabled while any bulk request is still pending, not only when >1 remain", async () => {
    // Regression test for the earlier isBulkInFlight > 1 derivation: once
    // exactly one bulk request remains, the panel used to flip out of bulk
    // mode and re-enable the controls.
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const deferreds = {};
    vi.spyOn(apiModule, "createLLMSuggestion").mockImplementation(
      (_config, _id, field) =>
        new Promise((resolve) => {
          deferreds[field] = resolve;
        }),
    );
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /enrich this resource/i }),
    );

    const holdOut = AI_SUGGESTION_FIELDS[AI_SUGGESTION_FIELDS.length - 1];
    await act(async () => {
      for (const field of AI_SUGGESTION_FIELDS) {
        if (field === holdOut) continue;
        deferreds[field]({
          resource_id: 1,
          field,
          value: `value-${field}`,
          citations: [],
          query_succeeded: true,
          model: "test-model",
          rationale: "Supported.",
          observed_at: "2026-05-13T12:00:00Z",
          foundry_request: {},
          foundry_response: {},
        });
      }
    });

    expect(screen.getByRole("button", { name: /enriching…/i })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /^cancel$/i }),
    ).toBeInTheDocument();
  });

  it("cancels an in-flight bulk run and does not surface aborted requests as errors", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const capturedSignals = [];
    vi.spyOn(apiModule, "createLLMSuggestion").mockImplementation(
      (_config, _id, _field, _fetcher, _endpoint, options) => {
        capturedSignals.push(options?.signal);
        return new Promise((resolve, reject) => {
          options?.signal?.addEventListener("abort", () => {
            const err = new Error("aborted");
            err.name = "AbortError";
            reject(err);
          });
        });
      },
    );
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /enrich this resource/i }),
    );
    await user.click(await screen.findByRole("button", { name: /^cancel$/i }));

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /^cancel$/i }),
      ).not.toBeInTheDocument(),
    );
    expect(capturedSignals.length).toBe(AI_SUGGESTION_FIELDS.length);
    for (const signal of capturedSignals) {
      expect(signal.aborted).toBe(true);
    }
    // Cancellation shouldn't render as a per-field failure.
    expect(
      screen.queryByText(/failed to generate suggestion/i),
    ).not.toBeInTheDocument();
    // Enrich returns to its idle label and is clickable again.
    expect(
      screen.getByRole("button", { name: /enrich this resource/i }),
    ).toBeEnabled();
  });

  it("tracks Add to resource loading state per field so concurrent attaches don't clobber each other", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    vi.spyOn(apiModule, "createLLMSuggestion").mockImplementation(
      async (_config, _id, field) => ({
        resource_id: 1,
        field,
        value: `value-${field}`,
        citations: [],
        query_succeeded: true,
        model: "test-model",
        rationale: "Supported.",
        observed_at: "2026-05-13T12:00:00Z",
        foundry_request: {},
        foundry_response: {},
      }),
    );
    // Two deferred creates so we can hold one open while another completes.
    const createDeferreds = [];
    vi.spyOn(apiModule, "createSourceForResource").mockImplementation(
      () =>
        new Promise((resolve) => {
          createDeferreds.push(resolve);
        }),
    );
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(
      screen.getByRole("button", { name: /enrich this resource/i }),
    );

    // Wait for the bulk run to settle so every "Add to resource" is present.
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: /add to resource/i }).length,
      ).toBe(AI_SUGGESTION_FIELDS.length),
    );

    const attachButtons = screen.getAllByRole("button", {
      name: /add to resource/i,
    });
    await user.click(attachButtons[0]);
    await user.click(attachButtons[1]);

    // Both requests are in flight and each field's own button reflects that.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /^adding…$/i }).length).toBe(
        2,
      ),
    );

    // Resolve only the first attach; the second field must stay in "Adding…"
    // until its own promise resolves — the bug we're guarding against would
    // clear that indicator here.
    await act(async () => {
      createDeferreds[0]({ id: 101, source: "llm" });
    });
    await screen.findByText("Source added to resource.");
    expect(screen.getAllByRole("button", { name: /^adding…$/i }).length).toBe(
      1,
    );

    await act(async () => {
      createDeferreds[1]({ id: 102, source: "llm" });
    });
    await waitFor(() =>
      expect(screen.getAllByText("Source added to resource.").length).toBe(2),
    );
  });
});
