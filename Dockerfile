# Build stage
FROM python:3.14-alpine AS builder

# Install build dependencies
RUN apk add build-base libffi-dev

# Install Poetry
RUN pip install poetry==1.5.1

# Set working directory
WORKDIR /build

# Copy project files needed for building
COPY pyproject.toml poetry.lock ./
COPY README.md ./
COPY src/ ./src/
COPY bin/ ./bin/

# Build wheel package
RUN poetry build -f wheel

# Runtime stage
FROM python:3.14-alpine

# Install dependencies
RUN apk add --no-cache \
    git \
    curl \
    jq \
    dotnet10-runtime \
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

# Set environment variables
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

ENTRYPOINT ["/github-action-entrypoint.sh"]