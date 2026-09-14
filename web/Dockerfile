
FROM node:20-alpine AS builder

WORKDIR /app

# Cache package dependencies
COPY package*.json ./
RUN npm ci

# Copy source code and build production bundle
COPY . .
RUN npm run build


# Stage 2: Hardened, unprivileged Nginx runtime
FROM nginx:alpine AS runtime

# Upgrade base packages and remove default static files
RUN apk update && apk upgrade --no-cache && \
    rm -rf /usr/share/nginx/html/*

# Create dedicated unprivileged user and group
RUN addgroup -g 10001 hawa && \
    adduser -u 10001 -G hawa -s /bin/false -D -H hawa

# Prepare writable runtime directories
RUN mkdir -p \
        /tmp/client_temp \
        /tmp/proxy_temp \
        /tmp/fastcgi_temp \
        /tmp/uwsgi_temp \
        /tmp/scgi_temp \
        /var/log/nginx \
        /var/run/nginx && \
    chown -R hawa:hawa \
        /tmp/client_temp \
        /tmp/proxy_temp \
        /tmp/fastcgi_temp \
        /tmp/uwsgi_temp \
        /tmp/scgi_temp \
        /var/log/nginx \
        /var/run/nginx \
        /etc/nginx \
        /usr/share/nginx/html

# Copy built static bundle
COPY --from=builder --chown=hawa:hawa \
    /app/dist /usr/share/nginx/html

# Replace the main Nginx configuration
COPY --chown=hawa:hawa \
    nginx-main.conf /etc/nginx/nginx.conf

# Copy server configuration
COPY --chown=hawa:hawa \
    nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script
COPY --chown=hawa:hawa \
    docker-entrypoint.sh /docker-entrypoint.sh

RUN chmod 755 /docker-entrypoint.sh

# Remove SUID/SGID bits
RUN find / -perm /6000 -type f -exec chmod a-s {} + 2>/dev/null || true

# Run as non-root
USER hawa:hawa

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]

CMD ["nginx", "-g", "daemon off;"]
