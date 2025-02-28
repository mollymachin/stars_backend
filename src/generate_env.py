#!/usr/bin/env python3
"""
Environment Configuration Generator for Star Map Backend

This script helps generate environment-specific configuration files
from the base .env.example template.
"""

import os
import sys
import shutil
import argparse
from typing import Dict, Any

ENV_EXAMPLE_FILE = ".env.example"
AVAILABLE_ENVIRONMENTS = ["development", "staging", "production", "test"]

# Environment-specific default overrides
ENV_DEFAULTS = {
    "development": {
        "DEBUG": "true",
        "API_CORS_ORIGINS": '["http://localhost:3000"]',
        "REDIS_HOST": "localhost",
        "LOG_LEVEL": "DEBUG",
    },
    "staging": {
        "DEBUG": "false",
        "API_CORS_ORIGINS": '["https://staging.yourappdomain.com"]',
    },
    "production": {
        "DEBUG": "false",
        "API_CORS_ORIGINS": '["https://yourappdomain.com"]',
        "LOG_LEVEL": "INFO",
    },
    "test": {
        "DEBUG": "true",
        "API_CORS_ORIGINS": '["*"]',
        "REDIS_HOST": "localhost",
        "LOG_LEVEL": "DEBUG",
    }
}

def read_env_file(file_path: str) -> Dict[str, str]:
    """Read an environment file and return a dictionary of key-value pairs"""
    env_vars = {}
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        print(f"Error reading {file_path}: {str(e)}")
        sys.exit(1)
        
    return env_vars

def write_env_file(file_path: str, env_vars: Dict[str, str]) -> None:
    """Write environment variables to a file"""
    try:
        with open(file_path, 'w') as f:
            f.write(f"# Generated configuration for {os.path.basename(file_path)}\n")
            f.write(f"# Generated on: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
                
        print(f"Successfully wrote configuration to {file_path}")
    except Exception as e:
        print(f"Error writing {file_path}: {str(e)}")
        sys.exit(1)

def generate_env_file(environment: str, output_file: str = None) -> None:
    """Generate an environment-specific configuration file"""
    if environment not in AVAILABLE_ENVIRONMENTS:
        print(f"Error: Unknown environment '{environment}'")
        print(f"Available environments: {', '.join(AVAILABLE_ENVIRONMENTS)}")
        sys.exit(1)
        
    # Default output filename if not specified
    if not output_file:
        output_file = f".env.{environment}"
        
    # Check if example file exists
    if not os.path.exists(ENV_EXAMPLE_FILE):
        print(f"Error: Example environment file '{ENV_EXAMPLE_FILE}' not found")
        print("Make sure you're running this script from the project root")
        sys.exit(1)
        
    # Check if output file already exists
    if os.path.exists(output_file):
        response = input(f"File '{output_file}' already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Operation cancelled")
            sys.exit(0)
            
    # Read the example file
    env_vars = read_env_file(ENV_EXAMPLE_FILE)
    
    # Apply environment-specific defaults
    if environment in ENV_DEFAULTS:
        for key, value in ENV_DEFAULTS[environment].items():
            env_vars[key] = value
            
    # Set the environment
    env_vars["ENVIRONMENT"] = environment
    
    # Write the new file
    write_env_file(output_file, env_vars)
    
def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(
        description="Generate environment-specific configuration files"
    )
    
    parser.add_argument(
        "environment", 
        choices=AVAILABLE_ENVIRONMENTS,
        help="Target environment to generate configuration for"
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: .env.<environment>)",
        default=None
    )
    
    args = parser.parse_args()
    generate_env_file(args.environment, args.output)
    
if __name__ == "__main__":
    main() 