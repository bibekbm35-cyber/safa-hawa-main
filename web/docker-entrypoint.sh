#!/bin/sh
set -e

# Default API URL is /api/v1 (works with reverse proxy or Ingress)
API_BASE_URL="${API_BASE_URL:-/api/v1}"

# Dynamically generate config.js from environment variable at container startup
cat <<EOF > /usr/share/nginx/html/config.js
window.__safa_HAWA__ = {
  apiBaseUrl: "${API_BASE_URL}",
};
EOF

# Hand over to CMD (typically nginx -g "daemon off;")
exec "$@"
