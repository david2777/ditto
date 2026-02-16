FROM ghcr.io/astral-sh/uv:0.6.11-python3.12-bookworm-slim

LABEL maintainer="daduvo11@gmail.com" \
  description="Ditto - A Notion-based quote service" \
  version="1.1.7"

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
  gcc \
  python3-dev \
  curl \
  imagemagick \
  libmagickwand-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install uv package manager and install dependencies
RUN uv pip install --system --no-cache .

# Expose port
EXPOSE 8000

# Set up health check
HEALTHCHECK --interval=300s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "ditto.main:app", "--host", "0.0.0.0", "--port", "8000"]

VOLUME /app/data