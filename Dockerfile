# Build stage
FROM python:3.14-alpine AS builder

# Install build dependencies
RUN apk add build-base libffi-dev

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /build

# Copy project files needed for building
COPY pyproject.toml uv.lock ./
COPY README.md ./
COPY src/ ./src/
COPY bin/ ./bin/

# Build wheel package
RUN uv build --wheel

# Runtime stage
FROM python:3.14-alpine

# Install dependencies
RUN apk add --no-cache \
    git \
    curl \
    jq \
    bash

# Set working directory
WORKDIR /app

# Copy the wheel file from the builder stage
COPY --from=builder /build/dist/*.whl /tmp/

# Install the wheel
RUN pip install /tmp/*.whl && rm /tmp/*.whl

# Copy entrypoint scripts
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

COPY github-action-entrypoint.sh /github-action-entrypoint.sh
RUN chmod +x /github-action-entrypoint.sh

RUN apk add --no-cache dotnet10-runtime gcompat
COPY bin/UnchainedScanner /usr/local/bin/UnchainedScanner
RUN chmod +x /usr/local/bin/UnchainedScanner

# Set environment variables
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV UNCHAINED_SCANNER_PATH=/usr/local/bin/UnchainedScanner

ENTRYPOINT ["/github-action-entrypoint.sh"]