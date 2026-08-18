/**
 * Field metadata dictionary.
 * Maps JSON payload keys to display configuration.
 * `section` groups fields into page sections on the detail view.
 */
export const FIELD_META = {
  // Identity & Location
  name: { label: "Name", section: "identity" },
  name_local: { label: "Local Name", section: "identity" },
  country: { label: "Country", section: "identity" },
  state_province: { label: "State / Province", section: "identity" },
  region: { label: "Region", section: "identity" },
  basin: { label: "Basin", section: "identity" },
  latitude: { label: "Latitude", section: "identity" },
  longitude: { label: "Longitude", section: "identity" },
  location_type: { label: "Location Type", section: "identity" },

  // Organizations
  owners: { label: "Owner", section: "organizations" },
  operators: { label: "Operator", section: "organizations" },

  // Production & Geology
  field_status: { label: "Field Status", section: "production" },
  production_conventionality: {
    label: "Production Conventionality",
    section: "production",
  },
  primary_hydrocarbon_group: {
    label: "Primary Hydrocarbon Group",
    section: "production",
  },
  reservoir_formation: { label: "Reservoir Formation", section: "production" },
  discovery_year: { label: "Discovery Year", section: "production" },
  production_start_year: {
    label: "Production Start Year",
    section: "production",
  },
  fid_year: { label: "FID Year", section: "production" },
};

export const IDENTITY_FIELDS = Object.entries(FIELD_META)
  .filter(([, v]) => v.section === "identity")
  .map(([k]) => k);

export const PRODUCTION_FIELDS = Object.entries(FIELD_META)
  .filter(([, v]) => v.section === "production")
  .map(([k]) => k);

/**
 * Fields always shown side by side in the Merge Review source comparison.
 * Order is display order.
 */
export const MERGE_COMPARISON_CORE_FIELDS = [
  "name",
  "country",
  "region",
  "basin",
  "state_province",
];

/**
 * Remaining scalar fields for the collapsed "Other attributes" accordion.
 * Organizations (owners/operators) are nested lists and are not compared.
 */
export const MERGE_COMPARISON_OTHER_FIELDS = Object.keys(FIELD_META).filter(
  (key) =>
    !MERGE_COMPARISON_CORE_FIELDS.includes(key) &&
    FIELD_META[key].section !== "organizations",
);

export const AI_SUGGESTION_FIELDS = [
  "name",
  "name_local",
  "country",
  "basin",
  "region",
  "state_province",
  "reservoir_formation",
  "discovery_year",
  "fid_year",
  "production_start_year",
  "location_type",
  "field_status",
  "primary_hydrocarbon_group",
  "production_conventionality",
];
