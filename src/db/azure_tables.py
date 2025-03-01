import time
import logging
from azure.data.tables import TableServiceClient
from azure.core.pipeline.policies import RetryPolicy, RetryMode
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Global table clients
tables = {}

# Configure retry policy for resilience
retry_policy = RetryPolicy(
    retry_mode=RetryMode.Exponential,
    backoff_factor=2,
    backoff_max=60,
    total_retries=5
)

def init_tables():
    """Initialize Azure Table Storage connections and tables"""
    global tables
    
    # Use managed identity if available, otherwise connection string
    connection_string = settings.AZURE.CONNECTION_STRING
    managed_identity_enabled = settings.AZURE.USE_MANAGED_IDENTITY

    if managed_identity_enabled:
        try:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            account_url = settings.AZURE.ACCOUNT_URL
            table_service_client = TableServiceClient(
                endpoint=account_url,
                credential=credential,
                retry_policy=retry_policy
            )
            logger.info("Using managed identity for Azure Table Storage authentication")
        except ImportError:
            logger.error("azure.identity not installed but managed identity is enabled")
            raise
    else:
        table_service_client = TableServiceClient.from_connection_string(
            connection_string,
            retry_policy=retry_policy
        )
        logger.info("Using connection string for Azure Table Storage authentication")

    # Initialize tables with retry logic
    for table_name in ["Users", "Stars", "UserStars"]:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                table_service_client.create_table_if_not_exists(table_name)
                tables[table_name] = table_service_client.get_table_client(table_name)
                logger.info(f"Successfully initialized table: {table_name}")
                break
            except Exception as e:
                if attempt == max_attempts - 1:
                    logger.error(f"Failed to initialize table {table_name} after {max_attempts} attempts: {str(e)}")
                    raise
                logger.warning(f"Failed to initialize table {table_name}, attempt {attempt+1}/{max_attempts}: {str(e)}")
                time.sleep(2 ** attempt)  # Exponential backoff

    return tables
