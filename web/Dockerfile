# Stage 1: Build static assets using Node
FROM node:20-alpine AS builder

WORKDIR /app

# Cache package dependencies
COPY package*.json ./
RUN npm ci

# Copy source code and build production bundle
COPY . .
RUN npm run build

# Stage 2: Hardened, unprivileged Nginx runtime (No Node.js, non-root UID 10001)
FROM nginx:alpine AS runtime

# Upgrade base packages to patch security advisories and remove default nginx static files
RUN apk update && apk upgrade --no-cache && \
    rm -rf /usr/share/nginx/html/*

# Create dedicated unprivileged non-root user and group (UID 10001)
RUN addgroup -g 10001 hawa && \
    adduser -u 10001 -G hawa -s /bin/false -D -H hawa

# Copy built static bundle from builder stage
COPY --from=builder --chown=hawa:hawa /app/dist /usr/share/nginx/html

# Copy custom hardened Nginx configuration
COPY --chown=hawa:hawa nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script for dynamic config injection
COPY --chown=hawa:hawa docker-entrypoint.sh /docker-entrypoint.sh

# Harden filesystem permissions for non-root execution
RUN chmod 755 /docker-entrypoint.sh && \
    touch /var/run/nginx.pid && \
    chown -R hawa:hawa /var/run/nginx.pid /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /usr/share/nginx/html && \
    chmod -R 775 /var/cache/nginx /var/log/nginx /var/run /usr/share/nginx/html && \
    # Remove any SUID/SGID bits to prevent privilege escalation
    find / -perm /6000 -type f -exec chmod a-s {} + 2>/dev/null || true

# Switch to unprivileged non-root user
USER hawa:hawa

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
