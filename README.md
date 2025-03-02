# Star Map Backend Service

A microservice for managing star objects in a star map application. This service provides APIs for managing stars, users, and user-star relationships, with real-time event streaming.

## Architecture

- **Backend**: FastAPI (Python)
- **Database**: Azure Table Storage
- **Cache**: Azure Redis Cache
- **Real-time Events**: Server-Sent Events (SSE)
- **Deployment**: Azure Container Apps
- **CI/CD**: GitHub Actions

## Key Features

- REST API for managing stars and users
- Real-time updates via Server-Sent Events
- Caching and rate limiting with Redis
- Modular and maintainable code structure
- Health checks and debug endpoints for monitoring
- Comprehensive configuration system
- Docker-based development and production environments

## Project Structure

```
├── src/                    # Source code directory
│   ├── api/                # API modules
│   │   ├── admin.py        # Admin-related endpoints
│   │   ├── debug.py        # Debug endpoints
│   │   ├── health.py       # Health check endpoints
│   │   ├── sse.py          # Server-Sent Events endpoints
│   │   ├── sse_publisher.py # SSE publisher utilities
│   │   ├── stars.py        # Stars API endpoints
│   │   └── users.py        # Users API endpoints
│   ├── config/             # Configuration management
│   │   └── settings.py     # Application settings
│   ├── db/                 # Database connections
│   │   ├── azure_tables.py # Azure Table Storage client
│   │   └── redis_cache.py  # Redis cache client
│   ├── dependencies/       # FastAPI dependencies
│   │   └── providers.py    # Dependency injection providers
│   ├── models/             # Pydantic models
│   │   ├── star.py         # Star model
│   │   └── user.py         # User model
│   ├── utils/              # Utility functions
│   ├── main.py             # FastAPI application setup
│   └── run.py              # Application entry point
├── tests/                  # Test directory
│   ├── api/                # API tests
│   ├── db/                 # Database tests
│   ├── models/             # Model tests
│   ├── util/               # Utility tests
│   └── conftest.py         # Test fixtures and configuration
├── scripts/                # Utility scripts
│   ├── migrate.py          # Migration utility
│   ├── cleanup.sh          # Cleanup script
│   └── setup_dev.sh        # Development setup script
├── config/                 # Configuration files
│   ├── .env.example        # Example environment file
│   ├── .env.development    # Development environment variables
│   └── pytest.ini          # pytest configuration
├── docker/                 # Docker-related files
│   ├── Dockerfile          # Main Dockerfile
│   ├── docker-compose.yml  # Main Docker Compose configuration
│   ├── docker-compose.dev.yml # Development Docker Compose
│   ├── docker-compose.prod.yml # Production Docker Compose
│   └── nginx/              # Nginx configuration
├── docs/                   # Documentation
│   ├── AZURE_DEPLOYMENT.md # Azure deployment documentation
│   └── api/                # API documentation
├── .github/                # GitHub workflows and actions
├── .vscode/                # VS Code configuration (optional)
├── probes.yaml             # Container health check configuration for Azure
└── run.py                  # Application entry point (root level for convenience)
```

## Project Reorganization Note

The project has been fully reorganized with a cleaner directory structure. All configuration files and Docker-related files are now in their respective directories:

### Configuration Files
- Environment files (`.env.example`, `.env.development`) are now in the `config/` directory
- Test configuration (`pytest.ini`) is now in the `config/` directory

### Docker Files
- All Docker-related files are now in the `docker/` directory:
  - `docker/Dockerfile`
  - `docker/docker-compose.yml`
  - `docker/docker-compose.dev.yml`
  - `docker/docker-compose.prod.yml`

### Running with New Structure
- Use `python run.py start` to start the application (unchanged)
- Use `python -m pytest -c config/pytest.ini` to run tests
- Use `docker compose -f docker/docker-compose.yml up` to run with Docker
- Use `docker compose -f docker/docker-compose.dev.yml up` for development

### CI/CD
- CI/CD workflows have been updated to use the new file locations

All symlinks that previously provided backward compatibility have been removed to fully commit to the new, cleaner organization structure.

### Files Remaining in Root Directory
A few essential files remain in the root directory for specific purposes:
- `run.py` - Main entry point for running the application
- `requirements.txt` - Python dependencies
- `probes.yaml` - Container health check configuration for Azure Container Apps

## Local Development

### Prerequisites
- Docker and Docker Compose
- Python 3.10+
- Azure Storage Account (or use Azurite for local development)
- Azure Redis Cache (optional for local development)

### Setup

1. Clone the repository
   ```bash
   git clone <your-repo-url>
   cd stars_backend
   ```

2. Set up your environment variables
   ```bash
   cp config/.env.example config/.env.development
   # Edit config/.env.development with your credentials
   ```

3. Start the application with Docker Compose
   ```bash
   docker compose -f docker/docker-compose.yml up
   ```

4. Access the API at http://localhost:8080

### Running without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application in development mode
python run.py dev
```

### Configuration Management

The application uses a comprehensive settings management system based on Pydantic:

1. **Configuration Files**:
   - `config/.env.example` - Template with all available settings
   - `config/.env.development` - Your local development settings
   - `config/.env.{environment}` - Environment-specific settings (development, staging, production, test)

2. **Environment-Specific Settings**:
   The system automatically applies appropriate defaults based on your environment:
   - `development` - Debugging enabled, localhost services
   - `staging` - Production-like with staging endpoints
   - `production` - Optimized for production use
   - `test` - Configuration for running tests

### Running Tests
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest -c config/pytest.ini
```

## Deployment

The application is deployed to Azure Container Apps using GitHub Actions.

### CI/CD Pipeline

1. The GitHub Action workflow builds and pushes the Docker image to GitHub Container Registry
2. The Azure Container App is configured to pull the latest image

### Manual Deployment

```bash
# Build and push the Docker image
docker buildx build -f docker/Dockerfile --platform linux/amd64 -t ghcr.io/<your-username>/astro-app-db:latest --push .

# Update the Azure Container App
az containerapp update \
  --name starmap-service \
  --resource-group starmap-rg \
  --image ghcr.io/<your-username>/astro-app-db:latest
```

## Environment Variables

The application uses a hierarchical configuration system with prefixed environment variables:

### Application Settings
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| ENVIRONMENT | Deployment environment (development, staging, production, test) | No | development |
| PORT | Application port | No | 8080 |
| DEBUG | Enable debugging features | No | false |
| PROJECT_NAME | API name for documentation | No | Star Map API |
| VERSION | API version | No | 1.1.0 |

### Azure Storage Settings (prefix: AZURE_STORAGE_)
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| CONNECTION_STRING | Connection string for Azure Table Storage | Yes* | - |
| ACCOUNT_URL | URL for Azure Storage account (used with managed identity) | Yes* | - |
| USE_MANAGED_IDENTITY | Whether to use Azure Managed Identity | No | false |

*Either CONNECTION_STRING or both USE_MANAGED_IDENTITY and ACCOUNT_URL must be provided.

### Redis Settings (prefix: REDIS_)
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| HOST | Redis hostname | Yes | - |
| PORT | Redis port | No | 6379 |
| PASSWORD | Redis access key | No | - |
| SSL | Whether to use SSL for Redis | No | false |
| CACHE_TTL | Default cache TTL in seconds | No | 300 |
| POPULAR_CACHE_TTL | Cache TTL for popular items in seconds | No | 3600 |
| POPULARITY_THRESHOLD | Threshold for considering an item popular | No | 50 |
| POPULARITY_WINDOW | Time window for popularity calculation in seconds | No | 3600 |

### API Settings (prefix: API_)
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| CORS_ORIGINS | List of allowed CORS origins in JSON format | No | ["http://localhost:3000"] |
| RATE_LIMIT_TIMES | Number of requests allowed in the time window | No | 5 |
| RATE_LIMIT_SECONDS | Time window for rate limiting in seconds | No | 60 |

### Logging Settings (prefix: LOG_)
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| LEVEL | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | No | INFO |
| FORMAT | Log format string | No | %(asctime)s - %(name)s - %(levelname)s - %(message)s |

## API Endpoints

### Health Checks
- `GET /health` - Overall health status
- `GET /health/liveness` - Container liveness check
- `GET /health/readiness` - Application readiness check

### Stars
- `GET /stars` - List all stars
- `POST /stars` - Create a new star
- `GET /stars/{star_id}` - Get a specific star
- `POST /stars/{star_id}/like` - Like a star
- `DELETE /stars/{star_id}` - Delete a star
- `GET /stars/active` - Get all active stars
- `GET /stars/popular` - Get popular stars

### Users
- `GET /users` - List all users
- `POST /users` - Create a new user
- `GET /users/{user_id}` - Get a specific user
- `PUT /users/{user_id}` - Update a user
- `DELETE /users/{user_id}` - Delete a user
- `GET /users/{user_id}/stars` - Get stars for a user

### Debug Endpoints
- `GET /debug/table-info` - Get information about Azure Tables
- `GET /debug/active-stars` - Diagnose issues with active stars 
- `POST /debug/add-test-star` - Add a test star for debugging

### Real-time Events (SSE)
- `GET /events/stars/stream` - Stream of real-time star events
- `GET /events/users/stream` - Stream of real-time user events

## Server-Sent Events

The application supports real-time updates through Server-Sent Events (SSE) for both stars and users:

### Star Events
```javascript
// Connect to the stars stream
const evtSource = new EventSource('/events/stars/stream');

// Handle incoming events
evtSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
  // data.type will be 'create', 'update', or 'delete'
  // data.data contains the star information
};
```

### User Events
```javascript
// Connect to the users stream
const evtSource = new EventSource('/events/users/stream');

// Handle incoming events
evtSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
  // data.type will be 'create', 'update', or 'delete'
  // data.data contains the user information
};
```

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify your connection strings and credentials in environment variables
   - Check if managed identity is properly configured (if using)

2. **Container Startup Issues**
   - Check logs with `az containerapp logs show --name starmap-service --resource-group starmap-rg`
   - Verify environment variables are properly set

3. **Local Development Issues**
   - Ensure Docker is running
   - Check `.env.development` file contains valid credentials
   - Make sure ports 8080, 6379, and 10000-10002 are available

4. **SSE Connection Issues**
   - Verify your client supports SSE
   - Check for CORS configuration if accessing from a different domain
   - Ensure the server can maintain long-lived connections

## License

[Your License]
