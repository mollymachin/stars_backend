#!/bin/bash
set -e

# Get the current timestamp for archiving
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Make sure the archive directory and its subdirectories exist
mkdir -p archive/database_versions
mkdir -p archive/deploy_configs
mkdir -p archive/docker_files
mkdir -p archive/env_files
mkdir -p archive/tests
mkdir -p archive/config_files

echo "Moving duplicate/unnecessary files to archive with timestamp: $TIMESTAMP"

# Files that should NOT be moved:
# - probes.yaml (important configuration file)
# - requirements.txt (needed at root level)
# - run.py (needed at root level)

# Only move the original Dockerfile if it exists alongside the one in docker/
if [ -f "Dockerfile" ] && [ -f "docker/Dockerfile" ]; then
    echo "Moving duplicate Dockerfile to archive/docker_files/"
    mv Dockerfile "archive/docker_files/Dockerfile_$TIMESTAMP"
else
    echo "No duplicate Dockerfile found."
fi

# Environment files that should be moved (including symlinks)
for env_file in ".env.docker" ".env.example" ".env.development"; do
    if [ -f "$env_file" ]; then
        if [ -L "$env_file" ]; then
            echo "Moving symlink $env_file to archive/env_files/"
            # Remove the symlink
            rm "$env_file"
            echo "Removed symlink $env_file, use config/$env_file directly"
        else
            echo "Moving $env_file to archive/env_files/"
            mv "$env_file" "archive/env_files/${env_file}_$TIMESTAMP"
        fi
    fi
done

# Move docker-compose symlinks
for compose_file in "docker-compose.yml" "docker-compose.dev.yml" "docker-compose.prod.yml"; do
    if [ -f "$compose_file" ]; then
        if [ -L "$compose_file" ]; then
            echo "Moving symlink $compose_file to archive/docker_files/"
            # Remove the symlink
            rm "$compose_file"
            echo "Removed symlink $compose_file, use docker/$compose_file directly"
        else
            echo "Moving $compose_file to archive/docker_files/"
            mv "$compose_file" "archive/docker_files/${compose_file}_$TIMESTAMP"
        fi
    fi
done

# Move pytest.ini symlink
if [ -f "pytest.ini" ] && [ -L "pytest.ini" ]; then
    echo "Moving symlink pytest.ini to archive/config_files/"
    rm "pytest.ini"
    echo "Removed symlink pytest.ini, use config/pytest.ini directly"
elif [ -f "pytest.ini" ] && [ ! -L "pytest.ini" ]; then
    echo "Moving pytest.ini to archive/config_files/"
    mv "pytest.ini" "archive/config_files/pytest.ini_$TIMESTAMP"
fi

# Check if stars.db exists and move it to database_versions (it's in .gitignore)
if [ -f "stars.db" ]; then
    echo "Moving stars.db to archive/database_versions/"
    mv stars.db "archive/database_versions/stars.db_$TIMESTAMP"
fi

# Check for reorganization files that are no longer needed
for reorg_file in "REORGANIZATION_PLAN.md" "REORGANIZATION_COMPLETE.md"; do
    if [ -f "$reorg_file" ]; then
        echo "Moving $reorg_file to archive/"
        mv "$reorg_file" "archive/${reorg_file}_$TIMESTAMP"
    fi
done

# Update .dockerignore to reference new folder structure if needed
if [ -f ".dockerignore" ]; then
    # Check if dockerignore needs to be updated with new paths
    if ! grep -q "docker/Dockerfile" .dockerignore; then
        echo ""
        echo "Updating .dockerignore with new paths"
        # Add new paths while preserving the existing file
        sed -i.bak 's/Dockerfile\*/docker\/Dockerfile\*/g' .dockerignore
        rm .dockerignore.bak
    else
        echo ".dockerignore already references new paths."
    fi
fi

# Create a file with instructions for the new structure
cat > "NEW_STRUCTURE_GUIDE.md" << EOF
# New Project Structure Guide

The project has been fully reorganized with a cleaner directory structure. Here's how to work with the new layout:

## Configuration Files
- Environment files (.env.example, .env.development) are now in the \`config/\` directory
- Test configuration (pytest.ini) is now in the \`config/\` directory

## Docker Files
- All Docker-related files are now in the \`docker/\` directory:
  - \`docker/Dockerfile\`
  - \`docker/docker-compose.yml\`
  - \`docker/docker-compose.dev.yml\`
  - \`docker/docker-compose.prod.yml\`

## Running the Application
- Use \`python run.py start\` to start the application (unchanged)
- Use \`python -m pytest\` to run tests (use \`-c config/pytest.ini\` if needed)
- Use \`docker compose -f docker/docker-compose.yml up\` to run with Docker
- Use \`docker compose -f docker/docker-compose.dev.yml up\` for development

## CI/CD
- CI/CD workflows have been updated to use the new file locations

The symlinks that previously provided backward compatibility have been removed to fully
commit to the new, cleaner organization structure.
EOF

echo ""
echo "Archive process complete. Symlinks and duplicate files have been moved to the archive folder."
echo "Created NEW_STRUCTURE_GUIDE.md with instructions for working with the new structure." 