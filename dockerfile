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

# Expose the FastAPI port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "database_service:app", "--host", "0.0.0.0", "--port", "8080"]

# Add metadata
LABEL org.opencontainers.image.source=https://github.com/hillcallum/stars_backend
LABEL org.opencontainers.image.description="Star Map Backend Service"
LABEL org.opencontainers.image.licenses=MIT