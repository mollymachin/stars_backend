# Azure Deployment Guide

This guide walks you through deploying the Star Map Backend Service to Azure using either GitHub Actions (automated) or manual deployment.

## Prerequisites

1. An Azure account with an active subscription
2. Azure CLI installed (for manual deployment)
3. GitHub repository with your code (for GitHub Actions)
4. Docker installed (for local testing and manual deployment)

## Required Azure Resources

You'll need to set up the following Azure resources:

1. **Resource Group** - to contain all resources
2. **Azure Table Storage** - for storing star and user data
3. **Azure Redis Cache** - for caching and rate limiting
4. **Azure Container App** - to host the API

## Option 1: Automated Deployment with GitHub Actions

### Step 1: Set up GitHub Secrets

In your GitHub repository, go to Settings > Secrets and add the following secrets:

- `AZURE_CREDENTIALS` - Service principal credentials in JSON format
- `AZURE_RESOURCE_GROUP` - Name of your resource group (e.g., "starmap-rg")
- `AZURE_LOCATION` - Azure region (e.g., "eastus")
- `AZURE_CONTAINER_ENV` - Container App environment name (e.g., "starmap-env")
- `AZURE_CONTAINER_APP` - Container App name (e.g., "starmap-api")
- `AZURE_STORAGE_CONNECTION_STRING` - Your Azure Storage connection string
- `REDIS_HOST` - Redis hostname
- `REDIS_PORT` - Redis port (usually 6380 for SSL)
- `REDIS_PASSWORD` - Redis access key
- `API_CORS_ORIGINS` - List of allowed CORS origins (e.g., `["https://yourdomain.com"]`)
- `ADMIN_API_KEY` - Secret key for admin endpoints

### Step 2: Create a Service Principal

```bash
# Login to Azure
az login

# Create a service principal and get credentials in JSON format
az ad sp create-for-rbac --name "starmap-github-action" --role contributor \
                          --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group} \
                          --sdk-auth
```

Copy the JSON output and save it as the `AZURE_CREDENTIALS` secret in GitHub.

### Step 3: Push to Main Branch

Push your code to the main branch to trigger the GitHub Actions workflow (or use the manual workflow dispatch).

## Option 2: Manual Deployment

### Step 1: Create Azure Resources

```bash
# Login to Azure
az login

# Set variables
RESOURCE_GROUP=starmap-rg
LOCATION=eastus
STORAGE_ACCOUNT=starmapstorage
REDIS_NAME=starmap-redis
CONTAINER_APP_ENV=starmap-env
CONTAINER_APP=starmap-api

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Storage Account
az storage account create --name $STORAGE_ACCOUNT --resource-group $RESOURCE_GROUP \
                           --location $LOCATION --sku Standard_LRS

# Get Storage connection string
STORAGE_CONNECTION_STRING=$(az storage account show-connection-string --name $STORAGE_ACCOUNT \
                              --resource-group $RESOURCE_GROUP --query connectionString -o tsv)

# Create Tables
az storage table create --name "Stars" --connection-string $STORAGE_CONNECTION_STRING
az storage table create --name "Users" --connection-string $STORAGE_CONNECTION_STRING
az storage table create --name "UserStars" --connection-string $STORAGE_CONNECTION_STRING

# Create Redis Cache
az redis create --resource-group $RESOURCE_GROUP --name $REDIS_NAME --location $LOCATION \
                 --sku Basic --vm-size c0

# Get Redis access key
REDIS_KEY=$(az redis list-keys --resource-group $RESOURCE_GROUP --name $REDIS_NAME --query primaryKey -o tsv)
REDIS_HOST=$REDIS_NAME.redis.cache.windows.net
REDIS_PORT=6380  # SSL port
```

### Step 2: Build and Push Docker Image

```bash
# Set variables
REGISTRY=ghcr.io
USERNAME=your-github-username
IMAGE_NAME=stars-backend
TAG=latest

# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login $REGISTRY -u $USERNAME --password-stdin

# Build the image
docker buildx build --platform linux/amd64 -t $REGISTRY/$USERNAME/$IMAGE_NAME:$TAG .

# Push the image
docker push $REGISTRY/$USERNAME/$IMAGE_NAME:$TAG
```

### Step 3: Deploy to Azure Container App

```bash
# Create Container App environment
az containerapp env create --name $CONTAINER_APP_ENV \
                           --resource-group $RESOURCE_GROUP \
                           --location $LOCATION

# Create Container App
az containerapp create \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image $REGISTRY/$USERNAME/$IMAGE_NAME:$TAG \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars \
    "ENVIRONMENT=production" \
    "PORT=8080" \
    "AZURE_STORAGE_CONNECTION_STRING=$STORAGE_CONNECTION_STRING" \
    "REDIS_HOST=$REDIS_HOST" \
    "REDIS_PORT=$REDIS_PORT" \
    "REDIS_PASSWORD=$REDIS_KEY" \
    "REDIS_SSL=true" \
    "API_CORS_ORIGINS=[\"https://yourdomain.com\"]" \
    "ADMIN_API_KEY=your-secret-key"
```

## Testing the Deployment

After deployment, you can test your API endpoints:

```bash
# Get the Container App URL
APP_URL=$(az containerapp show --name $CONTAINER_APP --resource-group $RESOURCE_GROUP \
                                --query properties.configuration.ingress.fqdn -o tsv)

# Test the health endpoint
curl https://$APP_URL/health

# Test the stars endpoint
curl https://$APP_URL/stars
```

## Monitoring and Logging

### Enable Application Insights (Optional)

```bash
# Create Application Insights
az monitor app-insights component create \
  --app starmap-insights \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Get the instrumentation key
APPINSIGHTS_KEY=$(az monitor app-insights component show \
                    --app starmap-insights \
                    --resource-group $RESOURCE_GROUP \
                    --query instrumentationKey -o tsv)

# Update Container App with instrumentation key
az containerapp update \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars "APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=$APPINSIGHTS_KEY"
```

### View Container App Logs

```bash
# View logs
az containerapp logs show \
  --name $CONTAINER_APP \
  --resource-group $RESOURCE_GROUP \
  --follow
```

## Troubleshooting

### Common Issues

1. **Container fails to start**:
   - Check logs with `az containerapp logs show`
   - Verify environment variables are correct
   - Ensure the Azure Storage and Redis services are accessible

2. **API returns 500 errors**:
   - Check application logs for exception details
   - Verify Azure Tables exist and are accessible
   - Test Redis connection

3. **Long startup times**:
   - Initial container startup may take time for cold starts
   - Consider increasing min-replicas for faster response

## Scaling and Production Considerations

1. **Scaling Rules**:
   - Add HTTP scaling rules for auto-scaling based on request volume:
   ```bash
   az containerapp update \
     --name $CONTAINER_APP \
     --resource-group $RESOURCE_GROUP \
     --scale-rule-name http-rule \
     --scale-rule-http-concurrency 50
   ```

2. **Custom Domain and SSL**:
   - Add a custom domain with SSL certificate:
   ```bash
   az containerapp hostname add \
     --name $CONTAINER_APP \
     --resource-group $RESOURCE_GROUP \
     --hostname yourdomain.com
     
   az containerapp certificate add \
     --name $CONTAINER_APP \
     --resource-group $RESOURCE_GROUP \
     --hostname yourdomain.com \
     --certificate-file cert.pfx \
     --password your-cert-password
   ```

## Cleanup

To remove all resources:

```bash
az group delete --name $RESOURCE_GROUP
``` 