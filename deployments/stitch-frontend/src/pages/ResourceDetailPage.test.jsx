import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAuth0 } from "@auth0/auth0-react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { auth0TestDefaults, renderWithQueryClient } from "../test/utils";
import ResourceDetailPage from "./ResourceDetailPage";
import { useResourceDetail, useSourceDetail } from "../hooks/useResources";
import * as apiModule from "../queries/api";

vi.mock("../hooks/useResources");

let mockedRouteId = "1";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: mockedRouteId }),
    useNavigate: () => vi.fn(),
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
    owners: [{ name: "Kuwait Oil Company", stake: 100 }],
    operators: [{ name: "Kuwait Oil Company", stake: 100 }],
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
  vi.mocked(useAuth0).mockReturnValue(auth0TestDefaults);
  vi.mocked(useResourceDetail).mockReturnValue({
    ...defaultHookReturn,
    refetch: vi.fn(),
  });
  vi.mocked(useSourceDetail).mockReturnValue(defaultSourceDetailHookReturn);
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
    expect(screen.getByText("Local Name")).toBeInTheDocument();
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

  it("shows source detail controls for each attached source", () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });

    renderWithQueryClient(<ResourceDetailPage />);

    expect(
      screen.getByRole("heading", { name: /source details/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /show details/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Burgan Source").length).toBeGreaterThan(0);
  });

  it("exposes disclosure accessibility attributes on the source detail toggle", async () => {
    vi.mocked(useResourceDetail).mockReturnValue({
      ...defaultHookReturn,
      data: mockDetailView,
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);

    const toggle = screen.getByRole("button", { name: /show details/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const panelId = toggle.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(panelId)).toBeTruthy();
  });

  it("renders raw source record details when a source detail panel is opened", async () => {
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
        country: "Kuwait",
        source_record_hash: "abc123",
        source_record: {
          producer: "stitch-seed@0.1.0",
          payload: { name: "Burgan Source" },
        },
      },
    });
    const user = userEvent.setup();

    renderWithQueryClient(<ResourceDetailPage />);
    await user.click(screen.getByRole("button", { name: /show details/i }));

    expect(await screen.findByText("Source Hash")).toBeInTheDocument();
    expect(screen.getByText("abc123")).toBeInTheDocument();
    expect(screen.getByText("stitch-seed@0.1.0")).toBeInTheDocument();
    expect(
      screen.getAllByText(/"name": "Burgan Source"/).length,
    ).toBeGreaterThan(0);
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
});
