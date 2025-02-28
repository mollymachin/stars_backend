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

3. Start the application with Docker Compose
   ```bash
   docker compose up
   ```

4. Access the API at http://localhost:80

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

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| AZURE_STORAGE_CONNECTION_STRING | Connection string for Azure Table Storage | Yes | - |
| AZURE_STORAGE_ACCOUNT_URL | URL for Azure Table Storage account | Yes | - |
| REDIS_HOST | Redis cache hostname | Yes | - |
| REDIS_PORT | Redis port | Yes | 6380 |
| REDIS_PASSWORD | Redis access key | Yes | - |
| REDIS_SSL | Whether to use SSL for Redis | Yes | true |
| USE_MANAGED_IDENTITY | Whether to use Azure Managed Identity | No | false |
| ENVIRONMENT | Deployment environment | No | production |
| PORT | Application port | No | 8080 |
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
