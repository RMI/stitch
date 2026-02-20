# api

## Deployment: Azure Container App

### Prerequisites

- Working local Docker environment (verify with `docker compose up --build`)
- Azure CLI installed and logged in (`az login`)
- `ACRPush` role on the target Azure Container Registry
- Existing PostgreSQL database provisioned and initialized (see `deployments/db/README.md`)
- Auth0 tenant and application configured

### Canonical Deployment Values (Example)

Replace these with environment-appropriate values.

```
SUBSCRIPTION=RMI-PROJECT-STITCH-SUB
RESOURCE_GROUP=STITCH-DEV-RG
REGISTRY=testdemostitchacr.azurecr.io
CONTAINER_APP_NAME=stitch-db-demo-02
IMAGE_NAME=stitch-api
VERSION=0.0.2
POSTGRES_HOST=stitch-deploy-test.postgres.database.azure.com
AUTH_ISSUER=https://rmi-spd.us.auth0.com/
AUTH_AUDIENCE=https://stitch-api.local
```

---

### Build and Push Image

Build the API image:

```bash
docker compose build api
```

Find the built image:

```bash
docker image ls
```

Tag and push:

```bash
REGISTRY="testdemostitchacr.azurecr.io"
VERSION="0.0.2"

docker tag <IMAGE_ID> "$REGISTRY/stitch-api:$VERSION"
az acr login -n "$REGISTRY"
docker push "$REGISTRY/stitch-api:$VERSION"
```

---

### Create Container App (Azure Portal)

#### Basics

- Subscription: `RMI-PROJECT-STITCH-SUB`
- Resource Group: `STITCH-DEV-RG`
- Name: `stitch-db-demo-02`
- Optimize for Azure Functions: Unchecked
- Deployment source: Container image
- Container Apps environment: As appropriate

#### Container

- Image: `<REGISTRY>/stitch-api:<VERSION>`
  - *Note on Auth*: This deploy assumes that the ACR has an admin user, as a workaround to developers not having permissions to grant `ACRPull` permissions to new resources.
- Workload Profile: Consumption
- CPU/Memory: 0.25 CPU / 0.5 GiB

Environment Variables:

```
LOG_LEVEL=info
POSTGRES_DB=stitch
POSTGRES_HOST=<POSTGRES_HOST>
POSTGRES_PORT=5432
POSTGRES_USER=stitch_app
POSTGRES_PASSWORD=*****
AUTH_DISABLED=false
AUTH_ISSUER=<AUTH_ISSUER>
AUTH_AUDIENCE=<AUTH_AUDIENCE>
AUTH_JWKS_URI=<AUTH_ISSUER>.well-known/jwks.json
```

#### Ingress

- Enabled
- Traffic: From anywhere

---

### Verify Deployment State

Get the "Application URL" from the resource overview.

Health check:

```
https://<CONTAINER_APP_URL>/api/v1/health
```

Expected:

```json
{"status":"ok"}
```

Authenticated endpoint test:

```
/api/v1/resources/2
```

Expected (no token):

```json
{"detail":"Missing Authorization header"}
```

This confirms:

- Container is running
- DB connection works
- Auth middleware is active

---

### Debugging

#### View Logs

Portal → Container App → Log Analytics → Logs → Switch to KQL Mode:

```KQL
ContainerAppConsoleLogs_CL
| project TimeGenerated, RevisionName_s, Stream_s, Log_s
```

#### Add New Revision

Edit container configuration.
Add or update environment variables.
Create revision and wait for rollout.

