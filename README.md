# Star Map API

A FastAPI backend service for the Star Map application, allowing users to create and interact with stars on a virtual sky map.

## Project Structure

The application follows a modular structure:

```
src/
├── api/               # API routes and endpoints
├── config/            # Configuration and settings
├── db/                # Database and storage connections
├── models/            # Pydantic models
├── utils/             # Utility functions
├── dependencies/      # Dependency injection
└── main.py            # Application entry point
```

## Setup and Development

### Prerequisites

- Python 3.10+
- Docker and Docker Compose (for local development)

### Local Development with Docker

1. Clone the repository:
   ```
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Set up environment variables:
   ```
   cp .env.development .env
   ```
   Edit `.env` to customize any settings.

3. Start the development environment:
   ```
   docker-compose up -d
   ```

4. Access the API at http://localhost:8080

### Manual Setup

1. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```
   cp .env.development .env
   ```
   Edit `.env` to customize any settings.

4. Start the application:
   ```
   uvicorn src.main:app --reload
   ```

## Migration from Legacy Structure

If you're migrating from the previous flat structure, follow these steps:

1. Run the migration script to backup your original files:
   ```
   python src/migrate.py
   ```
   
   To remove the original files after backup:
   ```
   python src/migrate.py --remove-originals
   ```

2. Review the new code structure and verify all functionality is working as expected.

3. Update any external references to the API endpoints.

## API Documentation

Once the server is running, API documentation is available at:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## Key Features

- **Star Management**: Create, retrieve, update, and delete stars
- **User Management**: User registration and management
- **Server-Sent Events**: Real-time updates for star actions
- **Caching**: Redis-based caching for popular stars
- **Rate Limiting**: Protect endpoints from abuse
- **Authentication**: Admin endpoints protected by API key

## Environment Variables

See `.env.development` for a complete list of available configuration options.
