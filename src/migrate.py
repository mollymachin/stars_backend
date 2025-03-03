#!/usr/bin/env python3
"""
Migration script to help transition from the old structure to the new modular structure.
This script will:
1. Create backup copies of original files in the appropriate archive subdirectories
2. Remove the original files (optionally)
3. Update imports in any files that need them
"""

import os
import shutil
import argparse
from datetime import datetime

# Files to archive (original flat structure) with their target subdirectory
ORIGINAL_FILES = [
    {"file": "database_service.py", "subdir": "database_versions"},
    {"file": "generate_env.py", "subdir": "env_files"},
    {"file": "validate_config.py", "subdir": "env_files"}
]

def ensure_archive_dirs(archive_base):
    """Ensure all required subdirectories exist in the archive"""
    subdirs = ["database_versions", "deploy_configs", "docker_files", "env_files"]
    for subdir in subdirs:
        full_path = os.path.join(archive_base, subdir)
        os.makedirs(full_path, exist_ok=True)
    return archive_base

def archive_files(archive_base, remove_originals=False):
    """Archive original files to appropriate subdirectories"""
    current_dir = os.path.dirname(__file__)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for file_info in ORIGINAL_FILES:
        filename = file_info["file"]
        subdir = file_info["subdir"]
        
        source_path = os.path.join(current_dir, filename)
        if os.path.exists(source_path):
            # Create archive filename with timestamp
            archive_filename = f"{os.path.splitext(filename)[0]}_{timestamp}{os.path.splitext(filename)[1]}"
            target_path = os.path.join(archive_base, subdir, archive_filename)
            
            # Create backup
            shutil.copy2(source_path, target_path)
            print(f"Backed up {filename} to {target_path}")
            
            # Remove original if requested
            if remove_originals:
                os.remove(source_path)
                print(f"Removed original {filename}")
        else:
            print(f"Warning: {filename} not found, skipping")

def main():
    parser = argparse.ArgumentParser(description="Migrate from original structure to modular structure")
    parser.add_argument('--remove-originals', action='store_true', 
                        help='Remove original files after creating backups')
    parser.add_argument('--archive-path', type=str, default='./archive',
                        help='Path to the archive directory (default: ./archive)')
    args = parser.parse_args()
    
    # Ensure archive directories exist
    archive_base = os.path.abspath(args.archive_path)
    ensure_archive_dirs(archive_base)
    print(f"Using archive directory: {archive_base}")
    
    # Archive files
    archive_files(archive_base, args.remove_originals)
    
    print("\nMigration complete!")
    print("Please update any imports in your code to use the new modular structure.")
    print("You may need to manually merge any custom changes from your original files.")

if __name__ == "__main__":
    main() 