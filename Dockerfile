FROM ghcr.io/astral-sh/uv:python3.12-slim

LABEL maintainer="daduvo11@gmail.com" \
      description="Ditto - A Notion-based quote service" \
      version="1.0.3"

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install uv package manager and install dependencies
RUN uv pip install --system --no-cache .

# Expose port
EXPOSE 8000

# Set up health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "ditto.main:app", "--host", "0.0.0.0", "--port", "8000"]

VOLUME /app/data