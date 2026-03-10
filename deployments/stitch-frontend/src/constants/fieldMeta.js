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
