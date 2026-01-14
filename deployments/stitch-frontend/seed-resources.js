// Seed script for resources endpoint
// Usage: node seed-resources.js

const API_BASE_URL =
  (typeof process !== "undefined" && process.env?.API_URL) ||
  "http://localhost:8000";
const RESOURCES_ENDPOINT = `${API_BASE_URL}/api/v1/resources/`;

const sampleResources = [
  { name: "Solar Farm Alpha", country: "USA" },
  { name: "Wind Turbine Beta", country: "Germany" },
  { name: "Hydroelectric Gamma", country: "Norway" },
  { name: "Geothermal Delta", country: "Iceland" },
  { name: "Solar Farm Epsilon", country: "Spain" },
  { name: "Wind Turbine Zeta", country: "Denmark" },
  { name: "Biomass Eta", country: "Brazil" },
  { name: "Tidal Theta", country: "UK" },
  { name: "Solar Farm Iota", country: "Australia" },
  { name: "Nuclear Kappa", country: "France" },
];

async function seedResource(resource) {
  try {
    const response = await fetch(RESOURCES_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(resource),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log(`✓ Created resource: ${data.name} (ID: ${data.id})`);
    return data;
  } catch (error) {
    console.error(
      `✗ Failed to create resource: ${resource.name}`,
      error.message,
    );
    throw error;
  }
}

async function seedAllResources() {
  console.log(`Starting to seed resources to ${RESOURCES_ENDPOINT}...\n`);

  try {
    for (const resource of sampleResources) {
      await seedResource(resource);
    }
    console.log(`\n✓ Successfully seeded ${sampleResources.length} resources!`);
  } catch (error) {
    console.error("\n✗ Seeding failed:", error.message);
    if (typeof process !== "undefined") {
      process.exit(1);
    }
  }
}

// Run the seeder
seedAllResources();
