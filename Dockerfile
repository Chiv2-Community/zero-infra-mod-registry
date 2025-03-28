FROM python:3.10-slim

# Install Poetry
RUN pip install poetry==1.5.1

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

# Set environment variables
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

ENTRYPOINT ["/docker-entrypoint.sh"]
