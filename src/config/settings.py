# Keep the existing settings classes with their validators
# LoggingSettings, AzureStorageSettings, RedisSettings, APISettings, AppSettings

import os
import socket
import logging
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List

##############################################################################
# Settings Classes
##############################################################################

class LoggingSettings(BaseSettings):
    LEVEL: str = Field("INFO", description="Logging level")
    FORMAT: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )
    
    model_config = SettingsConfigDict(env_prefix="LOG_")

class AzureStorageSettings(BaseSettings):
    CONNECTION_STRING: Optional[str] = Field(
        # Default to local Azurite connection string in development
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;" 
        if os.getenv('ENVIRONMENT', 'development') == 'development' else None,
        description="Azure Storage connection string"
    )
    ACCOUNT_URL: Optional[str] = Field(
        None, 
        description="Azure Storage account URL for managed identity"
    )
    USE_MANAGED_IDENTITY: bool = Field(
        False, 
        description="Whether to use Azure Managed Identity"
    )
    
    @field_validator("ACCOUNT_URL")
    def validate_account_url(cls, v, info):
        values = info.data
        if values.get("USE_MANAGED_IDENTITY") and not v:
            raise ValueError("AZURE_STORAGE_ACCOUNT_URL must be provided when USE_MANAGED_IDENTITY is enabled")
        return v
        
    model_config = SettingsConfigDict(env_prefix="AZURE_STORAGE_")

class RedisSettings(BaseSettings):
    # Make HOST optional with a default empty value for development
    HOST: Optional[str] = Field(
        "localhost" if os.getenv('ENVIRONMENT', 'development') == 'development' else None, 
        description="Redis host"
    )
    PORT: int = Field(6379, description="Redis port")
    PASSWORD: Optional[str] = Field(None, description="Redis password")
    SSL: bool = Field(False, description="Whether to use SSL for Redis connection")
    CACHE_TTL: int = Field(300, description="Default cache TTL in seconds")
    POPULAR_CACHE_TTL: int = Field(3600, description="Cache TTL for popular items")
    POPULARITY_THRESHOLD: int = Field(50, description="Threshold for considering an item popular")
    POPULARITY_WINDOW: int = Field(3600, description="Time window for popularity calculation in seconds")
    
    model_config = SettingsConfigDict(env_prefix="REDIS_")

class APISettings(BaseSettings):
    CORS_ORIGINS: List[str] = Field(
        ["http://localhost:3000"], # Default for development
        description="List of allowed CORS origins"
    )
    RATE_LIMIT_TIMES: int = Field(5, description="Number of requests allowed in the time window")
    RATE_LIMIT_SECONDS: int = Field(60, description="Time window for rate limiting in seconds")
    
    @field_validator('CORS_ORIGINS')
    def validate_cors_origins(cls, v, values):
        env = os.getenv('ENVIRONMENT', 'development')
        if env == 'production' and '*' in v:
            raise ValueError("Wildcard CORS origin '*' is not allowed in production")
        return v
    
    model_config = SettingsConfigDict(env_prefix="API_")

class AppSettings(BaseSettings):
    ENVIRONMENT: str = Field("development", description="Application environment")
    PORT: int = Field(8080, description="Application port")
    DEBUG: bool = Field(False, description="Debug mode")
    PROJECT_NAME: str = Field("Star Map API", description="Project name")
    VERSION: str = Field("1.1.0", description="API version")
    
    # Sub-settings
    AZURE: AzureStorageSettings = Field(default_factory=AzureStorageSettings)
    REDIS: RedisSettings = Field(default_factory=RedisSettings)
    LOGGING: LoggingSettings = Field(default_factory=LoggingSettings)
    API: APISettings = Field(default_factory=APISettings)
    
    # Host information for diagnostics
    HOST_NAME: str = Field(default_factory=socket.gethostname)
    
    @field_validator("ENVIRONMENT")
    def validate_environment(cls, v):
        allowed_environments = ["development", "staging", "production", "test"]
        if v not in allowed_environments:
            raise ValueError(f"Environment must be one of {allowed_environments}")
        return v
        
    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{os.getenv('ENVIRONMENT', 'development').lower()}"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Allow and ignore extra fields
    )

# Initialize settings once - MOVED TO THE END OF THE FILE
settings = AppSettings()

# Configure logging based on settings
logging.basicConfig(
    level=getattr(logging, settings.LOGGING.LEVEL),
    format=settings.LOGGING.FORMAT
)
logger = logging.getLogger(__name__)

# Log important configuration details
logger.info(f"Starting application in {settings.ENVIRONMENT} environment")
logger.info(f"Host: {settings.HOST_NAME}, Port: {settings.PORT}")

# Verify critical settings
def verify_required_settings():
    """Verify that all required settings are present and valid at startup"""
    critical_errors = []
    warnings = []
    
    # Check Azure Storage settings
    if not settings.AZURE.USE_MANAGED_IDENTITY and not settings.AZURE.CONNECTION_STRING:
        critical_errors.append(
            "Either AZURE_STORAGE_CONNECTION_STRING must be provided or AZURE_STORAGE_USE_MANAGED_IDENTITY must be enabled"
        )
        
    # Check Redis settings - warn but don't fail if Redis is not configured
    if not settings.REDIS.HOST:
        warnings.append("REDIS_HOST not configured. Caching and rate limiting will be disabled.")
        
    # Check API settings
    if settings.ENVIRONMENT == "production" and "*" in settings.API.CORS_ORIGINS:
        warnings.append("CORS is configured to allow all origins (*) in production environment")
            
    # Log warnings
    for warning in warnings:
        logger.warning(f"Configuration warning: {warning}")
        
    # Exit on critical errors
    if critical_errors:
        for error in critical_errors:
            logger.error(f"Configuration error: {error}")
        logger.error("Application startup failed due to configuration errors")
        import sys
        sys.exit(1)
