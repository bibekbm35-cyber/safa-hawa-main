# Stage 1: Build dependencies in isolated environment
FROM python:3.12-slim AS builder

WORKDIR /build

# Create virtual environment to isolate dependencies cleanly
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

# Copy pre-built virtual environment from builder stage
COPY --from=builder --chown=hawa:hawa /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code and migrations
COPY --chown=hawa:hawa alembic.ini .
COPY --chown=hawa:hawa alembic/ ./alembic/
COPY --chown=hawa:hawa app/ ./app/

# Hardening: Make application code read-only to prevent tampering at runtime
RUN chmod -R 555 /app

# Switch to non-root user
USER hawa:hawa

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
