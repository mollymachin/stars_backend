#!/usr/bin/env python3
"""
Helper script for running and managing the Star Map API.
Usage:
    python run.py [command]

Commands:
    start           Start the API server
    dev             Start the development server with auto-reload
    test            Run the test suite
    migrate         Run the migration script
    validate-config Validate the current configuration
    create-tables   Initialize database tables
    clean           Clean up temporary files and caches
"""

import os
import sys
import subprocess
import argparse
import shutil

def start_server(dev_mode=False):
    """Start the API server"""
    print(f"Starting {'development' if dev_mode else 'production'} server...")
    cmd = [
        "uvicorn", 
        "src.main:app", 
        "--host", "0.0.0.0", 
        "--port", os.environ.get("PORT", "8080")
    ]
    
    if dev_mode:
        cmd.append("--reload")
        
    subprocess.run(cmd)

def run_tests(coverage=False):
    """Run the test suite"""
    print("Running tests...")
    cmd = ["python", "-m", "pytest"]
    
    if coverage:
        cmd.extend(["--cov=src", "--cov-report=term", "--cov-report=html:coverage"])
        
    subprocess.run(cmd)

def run_migration(remove_originals=False, archive_path="./archive"):
    """Run the migration script"""
    print("Running migration script...")
    cmd = ["python", "scripts/migrate.py"]
    
    if remove_originals:
        cmd.append("--remove-originals")
        
    cmd.extend(["--archive-path", archive_path])
    
    subprocess.run(cmd)

def validate_config():
    """Validate the current configuration"""
    from src.config.settings import settings
    print("Validating configuration...")
    try:
        settings.verify_required_settings()
        print("Configuration is valid.")
    except Exception as e:
        print(f"Configuration error: {str(e)}")
        sys.exit(1)

def create_tables():
    """Initialize database tables"""
    from src.db.azure_tables import init_tables
    print("Initializing database tables...")
    init_tables()
    print("Database tables initialized.")

def clean():
    """Clean up temporary files and caches"""
    print("Cleaning up temporary files and caches...")
    
    # Clean up Python cache files
    for root, dirs, files in os.walk('.'):
        # Skip the venv directory
        if 'venv' in dirs:
            dirs.remove('venv')
        if '.git' in dirs:
            dirs.remove('.git')
            
        # Remove __pycache__ directories
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            print(f"Removing {pycache_path}")
            shutil.rmtree(pycache_path)
            dirs.remove('__pycache__')
            
        # Remove .pyc files
        for file in files:
            if file.endswith('.pyc'):
                file_path = os.path.join(root, file)
                print(f"Removing {file_path}")
                os.remove(file_path)
    
    print("Cleanup complete.")

def main():
    parser = argparse.ArgumentParser(description="Star Map API management script")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Start server command
    start_parser = subparsers.add_parser("start", help="Start the API server")
    
    # Dev server command
    dev_parser = subparsers.add_parser("dev", help="Start the development server with auto-reload")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Run the test suite")
    test_parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    
    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run the migration script")
    migrate_parser.add_argument("--remove-originals", action="store_true", 
                               help="Remove original files after backup")
    migrate_parser.add_argument("--archive-path", type=str, default="./archive",
                               help="Path to the archive directory")
    
    # Validate config command
    validate_parser = subparsers.add_parser("validate-config", help="Validate the current configuration")
    
    # Create tables command
    tables_parser = subparsers.add_parser("create-tables", help="Initialize database tables")
    
    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Clean up temporary files and caches")
    
    args = parser.parse_args()
    
    if args.command == "start":
        start_server(dev_mode=False)
    elif args.command == "dev":
        start_server(dev_mode=True)
    elif args.command == "test":
        run_tests(coverage=args.coverage)
    elif args.command == "migrate":
        run_migration(remove_originals=args.remove_originals, archive_path=args.archive_path)
    elif args.command == "validate-config":
        validate_config()
    elif args.command == "create-tables":
        create_tables()
    elif args.command == "clean":
        clean()
    else:
        parser.print_help()
        
if __name__ == "__main__":
    main() 