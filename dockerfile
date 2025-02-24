# Use lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy source code
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose necessary ports
EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "database_service:app", "--host", "0.0.0.0", "--port", "8000"]

# Add metadata
LABEL org.opencontainers.image.source=https://github.com/hillcallum/stars_backend
LABEL org.opencontainers.image.description="Star Map Backend Service"
LABEL org.opencontainers.image.licenses=MIT