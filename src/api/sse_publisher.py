"""
Publisher for Server-Sent Events.
This module provides functions to publish events to the SSE queues.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Union

# Import the event queues from the SSE module
from src.api.sse import star_event_queue, user_event_queue

logger = logging.getLogger(__name__)

async def publish_star_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Publish an event to the star event queue.
    
    Args:
        event_type: Type of event (e.g., 'create', 'update', 'delete')
        data: Event data containing star information
    """
    event = {
        "type": event_type,
        "data": data
    }
    
    try:
        await star_event_queue.put(event)
        logger.debug(f"Published star event: {event_type}")
    except Exception as e:
        logger.error(f"Failed to publish star event: {str(e)}")

async def publish_user_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Publish an event to the user event queue.
    
    Args:
        event_type: Type of event (e.g., 'create', 'update', 'delete')
        data: Event data containing user information
    """
    event = {
        "type": event_type,
        "data": data
    }
    
    try:
        await user_event_queue.put(event)
        logger.debug(f"Published user event: {event_type}")
    except Exception as e:
        logger.error(f"Failed to publish user event: {str(e)}")

# Non-async versions for use in synchronous code
def publish_star_event_sync(event_type: str, data: Dict[str, Any]) -> None:
    """
    Synchronous version of publish_star_event.
    Useful for contexts where you can't use async/await.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a task if we're already in an async context
            asyncio.create_task(publish_star_event(event_type, data))
        else:
            # Run in a new event loop if we're in a sync context
            asyncio.run(publish_star_event(event_type, data))
        logger.debug(f"Synchronously published star event: {event_type}")
    except Exception as e:
        logger.error(f"Failed to synchronously publish star event: {str(e)}")

def publish_user_event_sync(event_type: str, data: Dict[str, Any]) -> None:
    """
    Synchronous version of publish_user_event.
    Useful for contexts where you can't use async/await.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a task if we're already in an async context
            asyncio.create_task(publish_user_event(event_type, data))
        else:
            # Run in a new event loop if we're in a sync context
            asyncio.run(publish_user_event(event_type, data))
        logger.debug(f"Synchronously published user event: {event_type}")
    except Exception as e:
        logger.error(f"Failed to synchronously publish user event: {str(e)}") 