FROM node:20-alpine AS build
WORKDIR /app

# Install deps first (better caching)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY index.html vite.config.js ./
COPY public/ ./public/
COPY src/ ./src/

RUN ls -la

RUN npm run build

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

