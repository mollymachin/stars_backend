#!/bin/bash
set -e

# Create the directory first so we can put this script in it
mkdir -p scripts
if [ "$(basename "$0")" != "reorganize.sh" ]; then
    # Copy this script to scripts/ if it's not already there
    cp "$0" scripts/reorganize.sh
    chmod +x scripts/reorganize.sh
    echo "Copied reorganization script to scripts/reorganize.sh"
fi

echo "Starting project reorganization..."

# 1. Create new directories
echo "Creating new directories..."
mkdir -p config docker/nginx docs/api

# 2. Move files to appropriate directories
echo "Moving files to appropriate directories..."

# Scripts Directory
echo "Organizing scripts..."
if [ -f cleanup.sh ]; then 
    mv cleanup.sh scripts/
    echo "Moved cleanup.sh to scripts/"
fi

# Create setup script if it doesn't exist
if [ ! -f scripts/setup_dev.sh ]; then
    cat > scripts/setup_dev.sh << 'EOF'
#!/bin/bash
# Setup script for development environment
set -e

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Set up environment
echo "Setting up environment..."
if [ ! -f .env ]; then
    if [ -f config/.env.example ]; then
        cp config/.env.example .env
        echo "Created .env from example"
    else
        echo "Warning: No .env file created. Please create one manually."
    fi
fi

# Run tests to verify setup
echo "Running tests to verify setup..."
python -m pytest

echo "Development environment setup complete!"
EOF
    chmod +x scripts/setup_dev.sh
    echo "Created scripts/setup_dev.sh"
fi

# Move migration script if it exists
if [ -f migrate.py ]; then 
    mv migrate.py scripts/
    echo "Moved migrate.py to scripts/"
fi

# Config Directory
echo "Organizing configuration files..."
if [ -f pytest.ini ]; then 
    mv pytest.ini config/
    ln -sf config/pytest.ini pytest.ini
    echo "Moved pytest.ini to config/ and created symlink"
fi

if [ -f .env.example ]; then 
    mv .env.example config/
    ln -sf config/.env.example .env.example
    echo "Moved .env.example to config/ and created symlink"
fi

if [ -f .env.development ]; then 
    mv .env.development config/
    ln -sf config/.env.development .env.development
    echo "Moved .env.development to config/ and created symlink"
fi

# Docker Directory
echo "Organizing Docker files..."
if [ -f Dockerfile ]; then 
    mv Dockerfile docker/
    echo "Moved Dockerfile to docker/"
fi

if [ -f docker-compose.yml ]; then 
    mv docker-compose.yml docker/
    ln -sf docker/docker-compose.yml docker-compose.yml
    echo "Moved docker-compose.yml to docker/ and created symlink"
fi

if [ -f docker-compose.dev.yml ]; then 
    mv docker-compose.dev.yml docker/
    ln -sf docker/docker-compose.dev.yml docker-compose.dev.yml
    echo "Moved docker-compose.dev.yml to docker/ and created symlink"
fi

if [ -f docker-compose.prod.yml ]; then 
    mv docker-compose.prod.yml docker/
    ln -sf docker/docker-compose.prod.yml docker-compose.prod.yml
    echo "Moved docker-compose.prod.yml to docker/ and created symlink"
fi

# Move nginx directory if it exists
if [ -d nginx ] && [ "$(ls -A nginx)" ]; then
    mv nginx/* docker/nginx/
    rmdir nginx
    echo "Moved nginx configuration files to docker/nginx/"
fi

# Documentation Directory
echo "Organizing documentation..."
if [ -f AZURE_DEPLOYMENT.md ]; then 
    mv AZURE_DEPLOYMENT.md docs/
    echo "Moved AZURE_DEPLOYMENT.md to docs/"
fi

# Create an API documentation README if it doesn't exist
if [ ! -f docs/api/README.md ]; then
    mkdir -p docs/api
    cat > docs/api/README.md << 'EOF'
# API Documentation

This directory contains documentation for the APIs provided by this service.

## Endpoints

- `GET /api/stars` - List all stars
- `POST /api/stars` - Create a new star
- `GET /api/users` - List all users
- `POST /api/users` - Create a new user
- `GET /api/health` - Health check endpoint
- `GET /api/events` - Server-sent events endpoint

For more detailed documentation, refer to the OpenAPI documentation available at `/docs` when running the service.
EOF
    echo "Created docs/api/README.md"
fi

# 3. Update .gitignore to handle symlinks
echo "Updating .gitignore..."
if [ -f .gitignore ]; then
    # Make sure we don't ignore our symlinks
    if ! grep -q "# Symlinks - Don't ignore" .gitignore; then
        cat >> .gitignore << 'EOF'

# Symlinks - Don't ignore
!docker-compose*.yml
!.env.example
!.env.development
!pytest.ini
EOF
        echo "Updated .gitignore to keep symlinks"
    fi
fi

# 4. Create REORGANIZATION_COMPLETE.md
cat > REORGANIZATION_COMPLETE.md << 'EOF'
# Project Reorganization Complete

The project has been successfully reorganized with a more structured directory layout:

- `scripts/` - Utility and maintenance scripts
- `config/` - Configuration files
- `docker/` - Docker-related files
- `docs/` - Documentation

## Symlinks

Symlinks have been created for backward compatibility:
- `docker-compose.yml` → `docker/docker-compose.yml`
- `docker-compose.dev.yml` → `docker/docker-compose.dev.yml`
- `docker-compose.prod.yml` → `docker/docker-compose.prod.yml`
- `.env.example` → `config/.env.example`
- `.env.development` → `config/.env.development`
- `pytest.ini` → `config/pytest.ini`

## Next Steps

1. Update any CI/CD scripts to use the new file locations
2. Test the application to ensure everything still works
3. Consider additional organizational improvements as outlined in REORGANIZATION_PLAN.md

EOF

echo "Project reorganization complete! Please check REORGANIZATION_COMPLETE.md for details." 