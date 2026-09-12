# Stage 1: Build dependencies in isolated environment
FROM python:3.12-slim AS builder

WORKDIR /build

# Create virtual environment for isolated dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency definition first for optimal layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Hardened, minimal production runtime
FROM python:3.12-slim AS runtime

# Security Hardening:
# 1. Create a dedicated unprivileged non-root user (UID 10001)
# 2. Drop all SUID/SGID bits to eliminate privilege escalation vectors
# 3. Clean up package manager caches
RUN groupadd -g 10001 hawa && \
    useradd -u 10001 -g hawa -s /bin/false -m -d /app hawa && \
    find / -perm /6000 -type f -exec chmod a-s {} + 2>/dev/null || true && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=hawa:hawa /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy poller package
COPY --chown=hawa:hawa poller/ ./poller/

# Hardening: Make application code read-only to prevent tampering at runtime
RUN chmod -R 555 /app

# Switch to non-root user
USER hawa:hawa

# Expose Prometheus metrics port
EXPOSE 8001

CMD ["python", "-m", "poller.run"]
