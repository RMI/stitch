FROM node:20-alpine AS build
WORKDIR /app

# Install deps first (better caching)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY index.html vite.config.js ./
COPY public/ ./public/
COPY src/ ./src/

ARG VITE_AUTH0_DOMAIN
ARG VITE_AUTH0_CLIENT_ID
ARG VITE_AUTH0_AUDIENCE
ARG VITE_API_URL

ARG VITE_APP_ENV=production
ARG VITE_APP_VERSION
ARG VITE_BUILD_ID
ARG VITE_BUILD_TIME
ARG VITE_GIT_SHA
ARG VITE_NODE_VERSION
ARG VITE_VITE_VERSION

ENV VITE_AUTH0_DOMAIN=$VITE_AUTH0_DOMAIN \
    VITE_AUTH0_CLIENT_ID=$VITE_AUTH0_CLIENT_ID \
    VITE_AUTH0_AUDIENCE=$VITE_AUTH0_AUDIENCE \
    VITE_API_URL=$VITE_API_URL \
    VITE_APP_ENV=$VITE_APP_ENV \
    VITE_APP_VERSION=$VITE_APP_VERSION \
    VITE_BUILD_ID=$VITE_BUILD_ID \
    VITE_GIT_SHA=$VITE_GIT_SHA \
    VITE_NODE_VERSION=$VITE_NODE_VERSION \
    VITE_VITE_VERSION=$VITE_VITE_VERSION \
    VITE_BUILD_TIME=$VITE_BUILD_TIME

# --- derive build metadata if not provided ---
RUN \
  export VITE_APP_VERSION=${VITE_APP_VERSION:-$(node -p "require('./package.json').version")} && \
  export VITE_BUILD_ID=${VITE_BUILD_ID:-docker-local} && \
  export VITE_BUILD_TIME=${VITE_BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)} && \
  export VITE_NODE_VERSION=${VITE_NODE_VERSION:-$(node -p process.version)} && \
  export VITE_VITE_VERSION=${VITE_VITE_VERSION:-$(node -p "require('./package.json').devDependencies.vite")} && \
  npm run build

########################
# 2) Runtime stage (serve static files)
########################
FROM nginx:1.27-alpine AS runtime

# Optional: SPA routing configured via nginx.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

