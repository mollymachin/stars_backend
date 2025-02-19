# Use lightweight Python image
FROM python:3.11

# Set working directory
WORKDIR /app

# Copy source code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable for Azure Storage
ENV AZURE_STORAGE_CONNECTION_STRING="your_connection_string_here"

# Expose the FastAPI port
EXPOSE 5000

# Run the application
CMD ["uvicorn", "database_service:app", "--host", "0.0.0.0", "--port", "5000"]