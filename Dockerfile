# Build stage
FROM python:3.10-slim AS builder

# Install Poetry
RUN pip install poetry==1.5.1

# Set working directory
WORKDIR /build

# Copy project files needed for building
COPY pyproject.toml poetry.lock ./
COPY README.md ./
COPY src/ ./src/

# Build wheel package
RUN poetry build -f wheel

# Runtime stage
FROM python:3.10-slim

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl jq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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