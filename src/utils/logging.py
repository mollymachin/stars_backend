import logging
import sys
from src.config.settings import settings

def setup_logging():
    """
    Configure logging for the application based on settings
    """
    # Get log level from settings
    log_level = getattr(logging, settings.LOGGING.LEVEL.upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=settings.LOGGING.FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # Set level for specific loggers to reduce noise
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Create logger for our application
    logger = logging.getLogger("starmap")
    logger.setLevel(log_level)
    
    # Log startup information
    logger.info(f"Logging initialized at level {settings.LOGGING.LEVEL}")
    logger.info(f"Running in {settings.ENVIRONMENT} environment on {settings.HOST_NAME}")
    
    return logger
    
def get_logger(name):
    """Get a logger with the given name, inheriting application configuration"""
    return logging.getLogger(name)
