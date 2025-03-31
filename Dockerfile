FROM python:3.10-slim

# Install Poetry and other dependencies
RUN pip install poetry==1.5.1 && \
    apt-get update && \
    apt-get install -y --no-install-recommends git curl jq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY README.md ./
COPY src/ ./src/

# Configure Poetry
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy GitHub Action specific entrypoint
COPY github-action-entrypoint.sh /github-action-entrypoint.sh
RUN chmod +x /github-action-entrypoint.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

ENTRYPOINT ["/github-action-entrypoint.sh"]
