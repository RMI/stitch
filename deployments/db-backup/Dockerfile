# Nightly database backup: pg_dump + azcopy in one image.
#
# Published as ghcr.io/rmi/stitch-db-backup and run as an Azure Container Apps
# job (see job.yaml). The image holds no secrets; credentials arrive as env vars
# and a managed identity at run time.

# Keep the major version at or above the Postgres server's: pg_dump refuses to
# dump a server newer than itself.
FROM postgres:17-trixie

# azcopy is released as a prebuilt binary; pin the version and verify its
# checksum (the digest GitHub publishes for the release asset).
# Linux amd64 only, which is what the build workflow and Container Apps use.
ARG AZCOPY_VERSION=10.32.8
ARG AZCOPY_SHA256=a95277dbc265912cefdddbaf251aa99ec648cb18ba657e8788066357a9022dc3

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /tmp/azcopy.tar.gz \
      "https://github.com/Azure/azure-storage-azcopy/releases/download/v${AZCOPY_VERSION}/azcopy_linux_amd64_${AZCOPY_VERSION}.tar.gz" \
 && echo "${AZCOPY_SHA256}  /tmp/azcopy.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/azcopy.tar.gz --strip-components=1 -C /usr/local/bin \
      "azcopy_linux_amd64_${AZCOPY_VERSION}/azcopy" \
 && rm /tmp/azcopy.tar.gz \
 && azcopy --version

COPY deployments/db-backup/backup.sh /usr/local/bin/backup.sh

USER postgres
ENTRYPOINT ["/usr/local/bin/backup.sh"]
