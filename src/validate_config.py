#!/usr/bin/env python3
"""
Configuration validation script for Star Map Backend

This script validates the configuration settings from environment variables
and .env files to ensure the application will start correctly.
"""

import sys
import os
from pprint import pprint
from typing import Dict, Any, List, Tuple

# Add the parent directory to the path so we can import the settings class
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Import settings from the main app
    from src.database_service import AppSettings, verify_required_settings
    
    def check_config() -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Check the configuration and return a tuple of:
        (is_valid, warnings, config_values)
        """
        warnings = []
        errors = []
        
        try:
            # Load settings from environment
            settings = AppSettings()
            
            # Run the verification function
            try:
                verify_required_settings()
                is_valid = True
            except SystemExit:
                is_valid = False
                errors.append("Critical configuration errors found.")
                
            # Check common issues
            if settings.ENVIRONMENT == "production":
                if settings.DEBUG:
                    warnings.append("DEBUG mode is enabled in production environment")
                
                if "*" in settings.API.CORS_ORIGINS:
                    warnings.append("CORS is allowing all origins in production environment")
            
            # Get a sanitized view of the current configuration
            config_values = {
                "ENVIRONMENT": settings.ENVIRONMENT,
                "HOST_NAME": settings.HOST_NAME,
                "PORT": settings.PORT,
                "DEBUG": settings.DEBUG,
                "PROJECT_NAME": settings.PROJECT_NAME,
                "VERSION": settings.VERSION,
                "LOGGING": {
                    "LEVEL": settings.LOGGING.LEVEL,
                    "FORMAT": "<format string>",
                },
                "AZURE": {
                    "USE_MANAGED_IDENTITY": settings.AZURE.USE_MANAGED_IDENTITY,
                    "ACCOUNT_URL": settings.AZURE.ACCOUNT_URL,
                    "CONNECTION_STRING": "<hidden>" if settings.AZURE.CONNECTION_STRING else None,
                },
                "REDIS": {
                    "HOST": settings.REDIS.HOST,
                    "PORT": settings.REDIS.PORT,
                    "SSL": settings.REDIS.SSL,
                    "PASSWORD": "<hidden>" if settings.REDIS.PASSWORD else None,
                    "CACHE_TTL": settings.REDIS.CACHE_TTL,
                    "POPULAR_CACHE_TTL": settings.REDIS.POPULAR_CACHE_TTL,
                },
                "API": {
                    "CORS_ORIGINS": settings.API.CORS_ORIGINS,
                    "RATE_LIMIT_TIMES": settings.API.RATE_LIMIT_TIMES,
                    "RATE_LIMIT_SECONDS": settings.API.RATE_LIMIT_SECONDS,
                }
            }
            
            return is_valid, warnings + errors, config_values
            
        except Exception as e:
            return False, [f"Failed to load configuration: {str(e)}"], {}
    
    def main():
        """Main entry point for the script"""
        print("Star Map Backend Configuration Validator")
        print("=" * 50)
        
        is_valid, messages, config = check_config()
        
        # Print warnings and errors
        if messages:
            print("\nMessages:")
            for message in messages:
                print(f"  - {message}")
        
        # Print current configuration
        print("\nCurrent Configuration:")
        pprint(config, indent=2, width=100)
        
        # Print overall status
        print("\nValidation Result:", "✅ PASSED" if is_valid else "❌ FAILED")
        
        # Exit with appropriate code
        sys.exit(0 if is_valid else 1)
    
    if __name__ == "__main__":
        main()
        
except ImportError as e:
    print(f"Error importing settings from database_service.py: {str(e)}")
    print("Make sure you're running this script from the project root.")
    sys.exit(1) 