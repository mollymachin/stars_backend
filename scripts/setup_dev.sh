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
