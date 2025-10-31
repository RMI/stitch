# Stitch Architecture

## Project Structure

`stitch` is organized as a monorepo. This allows for clean separation of core components & functionality, deployed applications and services, and development/deployment support features.

**`packages/`**

- Contains the various core components and domain logic in separate, versioned packages

**`deployments/`**

- Houses our deployable applications and any public, published packages

**`dev/`**

- Contains miscellaneous development support tooling and scripts
