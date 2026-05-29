# syntax=docker/dockerfile:1

# ---- builder: produce a wheel ----
FROM python:3.12-slim-bookworm AS builder
RUN pip install --no-cache-dir uv
WORKDIR /build
# Copy only what the build backend (hatchling) needs to produce the wheel.
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv build --wheel --out-dir /wheels

# ---- runtime ----
FROM python:3.12-slim-bookworm AS runtime
# OpenCV (headless) needs libglib2.0-0; libgomp1 backs numpy/opencv threading.
# tini reaps zombies + forwards signals (compose also sets init: true).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 tini \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

# Install curbcam into the SYSTEM python (no venv) from the built wheel.
# The [picamera2] extra is deliberately NOT installed — Pi Camera Module
# support in Docker is deferred (spec §2.2). USB/RTSP/file work here.
COPY --from=builder /wheels/*.whl /tmp/wheels/
RUN uv pip install --system --no-cache /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Alembic config + migration scripts live at the repo root (outside the wheel),
# so copy them in — `curbcam db upgrade` needs them at runtime.
WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz').status == 200 else 1)"

# Runs as root: single-purpose appliance, zero-fuss camera device access (spec §7.1).
ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh"]
