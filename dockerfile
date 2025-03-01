# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir azure.identity>=1.10.0 && \
    pip install --no-cache-dir pydantic-settings>=2.0.0

# Create necessary directories
RUN mkdir -p /app/src /app/logs

# Copy application code
COPY src/ /app/src/
COPY .env.example .

# Create a non-root user and switch to it
RUN adduser --disabled-password --gecos "" appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Command to run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]

# Add metadata
LABEL org.opencontainers.image.source=https://github.com/hillcallum/stars_backend
LABEL org.opencontainers.image.description="Star Map Backend Service"
LABEL org.opencontainers.image.licenses=MIT