import asyncio
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Create event queues for SSE
star_event_queue = asyncio.Queue()
user_event_queue = asyncio.Queue()

@router.get("/stars/stream")
async def stream_stars(request: Request):
    """
    SSE endpoint that emits star add/remove events.
    If no event occurs within 15 seconds, send a keep-alive comment.
    """
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(star_event_queue.get(), timeout=15.0)
                yield f"data: {event}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/users/stream")
async def stream_users(request: Request):
    """
    SSE endpoint that emits user events.
    If no event occurs within 15 seconds, send a keep-alive comment.
    """
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(user_event_queue.get(), timeout=15.0)
                yield f"data: {event}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
