# Star Map Backend Service

A microservice for managing celestial objects in a star map application. This service provides APIs for managing stars, users, and user-star relationships.

## Architecture

- **Backend**: FastAPI (Python)
- **Database**: Azure Table Storage
- **Cache**: Azure Redis Cache
- **Deployment**: Azure Container Apps
- **CI/CD**: GitHub Actions

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
   cp .env.example .env
   # Edit .env with your credentials
   ```

   Or use our configuration generator:
   ```bash
   python -m src.generate_env development
   ```

3. Start the application with Docker Compose
   ```bash
   docker compose up
   ```

4. Access the API at http://localhost:80

### Configuration Management

The application uses a comprehensive settings management system based on Pydantic:

1. **Configuration Files**:
   - `.env.example` - Template with all available settings
   - `.env` - Your local development settings
   - `.env.{environment}` - Environment-specific settings (development, staging, production, test)

2. **Configuration Utilities**:
   - `src/generate_env.py` - Generate environment-specific configuration files
   ```bash
   # Generate a development configuration
   python -m src.generate_env development
   
   # Generate a production configuration
   python -m src.generate_env production -o .env.prod
   ```
   
   - `src/validate_config.py` - Validate your current configuration
   ```bash
   # Validate your current configuration
   python -m src.validate_config
   ```

3. **Configuration Groups**:
   - Application settings - Core application settings
   - Azure Storage settings - Database configuration
   - Redis settings - Caching and rate limiting
   - API settings - CORS, rate limiting, etc.
   - Logging settings - Log levels and formats

4. **Environment-Specific Settings**:
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
pytest
```

## Deployment

The application is deployed to Azure Container Apps using GitHub Actions.

### CI/CD Pipeline

1. The GitHub Action workflow builds and pushes the Docker image to GitHub Container Registry
2. The Azure Container App is configured to pull the latest image

### Manual Deployment

```bash
# Build and push the Docker image
docker buildx build --platform linux/amd64 -t ghcr.io/<your-username>/astro-app-db:latest --push .

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
| CORS_ORIGINS | List of allowed CORS origins in JSON format | No | ["*"] |
| RATE_LIMIT_TIMES | Number of requests allowed in the time window | No | 5 |
| RATE_LIMIT_SECONDS | Time window for rate limiting in seconds | No | 60 |

### Logging Settings (prefix: LOG_)
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| LEVEL | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | No | INFO |
| FORMAT | Log format string | No | %(asctime)s - %(name)s - %(levelname)s - %(message)s |

### Other Settings
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| AZURE_MONITORING | Enable Azure monitoring | No | false |

## API Endpoints

### Health Checks
- `GET /health` - Overall health status
- `GET /health/liveness` - Container liveness check
- `GET /health/readiness` - Application readiness check

### Stars
- `GET /stars` - List all stars
- `POST /stars` - Create a new star
- `GET /stars/{star_id}` - Get a specific star
- `PUT /stars/{star_id}` - Update a star
- `DELETE /stars/{star_id}` - Delete a star

### Users
- `GET /users` - List all users
- `POST /users` - Create a new user
- `GET /users/{user_id}` - Get a specific user
- `PUT /users/{user_id}` - Update a user
- `DELETE /users/{user_id}` - Delete a user

### User-Star Relationships
- `GET /users/{user_id}/stars` - Get stars for a user
- `POST /users/{user_id}/stars/{star_id}` - Add a star to a user's collection
- `DELETE /users/{user_id}/stars/{star_id}` - Remove a star from a user's collection

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
   - Check `.env` file contains valid credentials

## License

[Your License]
