import redis
import json
import time
import asyncio
import uuid
import os
import math
import logging

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from fastapi.openapi.docs import get_swagger_ui_html
from redis import asyncio as aioredis
from pydantic import BaseModel
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import stats as stats_module
from sqlalchemy import create_engine, Column, Integer, Float, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from datetime import datetime, UTC
from typing import Optional

load_dotenv()




# Comment out legacy SQLite + SQLAlchemy code for local development

'''

##############################################################################
# 1) Database Setup (SQLite + SQLAlchemy)
##############################################################################
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./stars.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()

class StarDB(Base):
    __tablename__ = "stars"
    id = Column(Integer, primary_key=True, index=True)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    message = Column(String, nullable=False)

Base.metadata.create_all(bind=engine)
'''

##############################################################################
# 2) Azure Table Storage Setup
##############################################################################

connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
table_service_client = TableServiceClient.from_connection_string(connection_string)

# Create or get tables
tables = {}
for table_name in ["Users", "Stars", "UserStars"]:
    try:
        tables[table_name] = table_service_client.create_table_client(table_name)
    except ResourceNotFoundError:
        tables[table_name] = table_service_client.get_table_client(table_name)


##############################################################################
# 3) Pydantic Models
##############################################################################

class Star(BaseModel):
    id: Optional[str] = None
    x: float
    y: float
    message: str
    brightness: Optional[float] = 100.0
    last_liked: Optional[float] = None

class User(BaseModel):
    id: Optional[str] = None
    name: str
    email: str
    created_at: Optional[datetime] = None

##############################################################################
# 4) SSE Event Queue
##############################################################################

star_event_queue = asyncio.Queue()
user_event_queue = asyncio.Queue()

##############################################################################
# 5) FastAPI App with Azure Table Storage
##############################################################################

app = FastAPI()

@app.post("/users")
async def create_user(user: User):
    user_id = str(uuid.uuid4())
    user_entity = {
        "PartitionKey": "USER",
        "RowKey": user_id,
        "Username": user.name,
        "Email": user.email,
        "CreatedAt": datetime.now(UTC).isoformat()
    }
    tables["Users"].create_entity(user_entity)
    return {"user_id": user_id, **user.dict()}

@app.post("/stars")
async def add_star(star: Star):
    current_time = datetime.now(UTC).timestamp()
    star_entity = {
        "PartitionKey": f"STAR_{datetime.now(UTC).strftime('%Y%m')}",
        "RowKey": str(uuid.uuid4()),
        "X": star.x,
        "Y": star.y,
        "Message": star.message,
        "Brightness": 100.0, # Default brightness
        "LastLiked": current_time,
        "CreatedAt": current_time
    }
    tables["Stars"].create_entity(star_entity)

    # Push SSE event 
    await star_event_queue.put({
        "event": "add",
        "star": {
            "id": star_entity["RowKey"],
            "x": star.x,
            "y": star.y,
            "message": star.message,
            "brightness": star.brightness,
            "last_liked": current_time
        }
    })
    return star_entity

##############################################################################
# 6) Redis Cache Configuration
##############################################################################

CACHE_TTL_SECONDS = 300 # Regular cache TTL
POPULAR_CACHE_TTL_SECONDS = 3600 # Longer TTL for popular items
POPULARITY_THRESHOLD = 50 # Minimum likes to be considered "popular"
POPULARITY_WINDOW_SECONDS = 3600 # Time window for popularity calculation

@app.on_event("startup")
async def startup():
    # Add this to your existing startup function
    redis_host = os.getenv("REDIS_HOST")
    redis_password = os.getenv("REDIS_PASSWORD")
    redis_url = f"redis://{redis_host}:6379"
    
    redis = aioredis.from_url(
        redis_url,
        password=redis_password,
        encoding="utf8",
        decode_responses=True
    )
    FastAPICache.init(
        backend=RedisBackend(redis),
        prefix="starmap-cache"
    )

##############################################################################
# 7) CRUD + SSE Endpoints
##############################################################################

@app.get("/stars")
async def get_stars():
    """Return all stars with their current brightness."""
    stars = tables["Stars"].query_entities(query_filter="PartitionKey eq 'STAR'")
    current_time = datetime.now(UTC).timestamp()
    
    return [{
        "id": star["RowKey"],
        "x": star["X"],
        "y": star["Y"],
        "message": star["Message"],
        "brightness": calculate_current_brightness(star["Brightness"], star["LastLiked"]),
        "last_liked": star["LastLiked"]
    } for star in stars]

@app.get("/stars/{star_id}")
@cache(expire=CACHE_TTL_SECONDS)
async def get_star(star_id: str):
    """Get a specific star with automatic caching."""
    try:
        # Check if it's in Redis first
        redis = FastAPICache.get_backend().client
        popularity_key = f"star_popularity:{star_id}"
        recent_likes = await redis.get(popularity_key)
        
        star = tables["Stars"].get_entity(partition_key="STAR", row_key=star_id)
        current_brightness = calculate_current_brightness(
            star["Brightness"],
            star["LastLiked"]
        )
        
        response = {
            "id": star["RowKey"],
            "x": star["X"],
            "y": star["Y"],
            "message": star["Message"],
            "brightness": current_brightness,
            "last_liked": star["LastLiked"],
            "is_popular": recent_likes is not None and int(recent_likes) >= POPULARITY_THRESHOLD
        }

        # If star is popular, update cache with longer TTL
        if response["is_popular"]:
            await FastAPICache.get_backend().set(
                f"star:{star_id}",
                json.dumps(response),
                expire=POPULAR_CACHE_TTL_SECONDS
            )
            
        return response
    except:
        raise HTTPException(status_code=404, detail="Star not found")

@app.post("/stars/{star_id}/like")
async def like_star(star_id: str):
    """Like a star and update popularity metrics."""
    try:
        star = tables["Stars"].get_entity(partition_key="STAR", row_key=star_id)
        current_time = datetime.now(UTC).timestamp()
        
        # Update the star's brightness and last_liked time
        star["Brightness"] = min(100.0, star["Brightness"] + 20.0)
        star["LastLiked"] = current_time
        
        # Update popularity counter in Redis
        redis = FastAPICache.get_backend().client
        popularity_key = f"star_popularity:{star_id}"
        
        # Increment likes counter with expiry
        await redis.incr(popularity_key)
        await redis.expire(popularity_key, POPULARITY_WINDOW_SECONDS)
        
        # Invalidate the star's cache to force refresh
        await FastAPICache.get_backend().delete(f"star:{star_id}")

        tables["Stars"].update_entity(star)
        
        # Push SSE event
        await star_event_queue.put({
            "event": "update",
            "star": {
                "id": star_id,
                "brightness": star["Brightness"],
                "last_liked": current_time
            }
        })
        
        return star
    except:
        raise HTTPException(status_code=404, detail="Star not found")

def calculate_current_brightness(base_brightness: float, last_liked: float) -> float:
    time_since_liked = datetime.now(UTC).timestamp() - last_liked
    decay_factor = max(0.01, 1.0 - 0.01 * time_since_liked)
    return max(20.0, base_brightness * math.exp(-decay_factor * time_since_liked))

@app.get("/stars/popular")
@cache(expire=30)
async def get_popular_stars():
    """Get currently popular stars."""
    redis = FastAPICache.get_backend().client
    
    # Get all popularity counters
    keys = await redis.keys("star_popularity:*")
    popular_stars = []
    
    for key in keys:
        star_id = key.split(":")[1]
        likes = int(await redis.get(key) or 0)
        
        if likes >= POPULARITY_THRESHOLD:
            try:
                star = await get_star(star_id)
                popular_stars.append(star)
            except HTTPException:
                continue
            
    return sorted(popular_stars, key=lambda x: x["brightness"], reverse=True)

@app.get("/stars/batch/{star_ids}")
async def get_stars_batch(star_ids: str):
    """Get multiple stars in a single request."""
    ids = star_ids.split(",")
    stars = []
    
    for star_id in ids:
        try:
            star = await get_star(star_id.strip())
            stars.append(star)
        except HTTPException:
            continue
    
    return stars

@app.get("/stats/cache")
async def get_cache_stats():
    """Get cache statistics."""
    redis = FastAPICache.get_backend().client
    
    # Get cache stats
    info = await redis.info()
    
    return {
        "hits": info["keyspace_hits"],
        "misses": info["keyspace_misses"],
        "hit_rate": info["keyspace_hits"] / (info["keyspace_hits"] + info["keyspace_misses"]),
        "popular_stars": len([k for k in await redis.keys("star_popularity:*")]),
        "memory_used": info["used_memory_human"]
    }

@app.delete("/stars/{star_id}")
async def remove_star(star_id: str):
    "Remove a star by ID and push an SSE event"
    try:
        star = tables["Stars"].get_entity(partition_key="STAR", row_key=star_id)
        tables["Stars"].delete_entity(partition_key="STAR", row_key=star_id)

        # Push SSE event
        await star_event_queue.put({
            "event": "remove",
            "star": {
                "id": star_id,
                "x": star["X"],
                "y": star["Y"],
                "message": star["Message"]
            }
        })

        return {"message": f"Star {star_id} successfully removed"}
    except Resou:
        raise HTTPException(status_code=404, detail=f"Star with ID {star_id} not found")
    
@app.delete("/stars")
async def remove_all_stars():
    "Remove all stars and push an SSE event (NB!!! Dangerous! Only for admins)"
    # TODO: Add admin authentication
    stars = tables["Stars"].query_entities(query_filter="PartitionKey eq 'STAR'")
    for star in tables["Stars"].query_entities(query_filter="PartitionKey eq 'STAR'"):
        tables["Stars"].delete_entity(partition_key="STAR", row_key=star["RowKey"])

    # Push SSE event
    await star_event_queue.put({
        "event": "remove_all"        
    })

    return {"message": "All stars removed"}

@app.get("stars/stream")
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

@app.get("/stars/active")
@cache(expire=300)
async def get_active_stars():
    """Get all stars that have been liked recently."""
    current_time = datetime.now(UTC).timestamp()
    cutoff_time = current_time - POPULARITY_WINDOW_SECONDS  # Only include stars liked in the last hour

    # Query Azure Table Storage for stars
    query_filter = f"LastLiked ge {cutoff_time}"
    stars = tables["Stars"].query_entities(query_filter=query_filter)

    return [
        {
            "id": star["RowKey"],
            "x": star["X"],
            "y": star["Y"],
            "message": star["Message"],
            "brightness": calculate_current_brightness(star["Brightness"], star["LastLiked"]),
            "last_liked": star["LastLiked"]
        }
        for star in stars
    ]

##############################################################################
# 8) Azure Monitor Metrics
##############################################################################

exporter = metrics_exporter.new_metrics_exporter()
stats_recorder = stats_module.stats_recorder

# Add performance monitoring
@app.middleware("http")
async def add_monitoring(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Log request duration
    logger.info(f"Request to {request.url.path} took {duration:.2f} seconds")
    return response

# Add health checks
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.1",
        "timestamp": datetime.now(UTC).timestamp()
    }

##############################################################################
# 9) Azure Container App Configuration
##############################################################################

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

##############################################################################
# 10) Documentation
##############################################################################

@app.get("/docs")
async def get_documentation():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Astro App Backend API Documentation"
    )

# Comment out legacy SQLite + SQLAlchemy code for local development

'''

##############################################################################
# 4) Startup Event: Pre-populate DB if empty
##############################################################################
@app.on_event("startup")
def startup_populate_db():
    with SessionLocal() as db:
        # Check if there's any star in the DB
        count = db.query(StarDB).count()
        if count == 0:
            print("No stars in DB. Pre-populating with some fake data.")
            initial_data = [
                StarDB(x=0.5, y=0.5, message="Alpha Star"),
                StarDB(x=-0.4, y=0.1, message="Beta Star"),
                StarDB(x=0.0, y=-0.7, message="Gamma Star"),
            ]
            db.add_all(initial_data)
            db.commit()
'''

# Comment out legacy SQLite + SQLAlchemy code for local development

'''
##############################################################################
# 5) Dependency for DB session
##############################################################################
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

# Comment out legacy SQLite + SQLAlchemy code for local development

'''

##############################################################################
# 6) CRUD + SSE Endpoints
##############################################################################

@app.get("/stars")
def get_stars(db: Session = Depends(get_db)):
    """
    Return all stars from the DB.
    """
    results = db.query(StarDB).all()
    return [Star(id=s.id, x=s.x, y=s.y, message=s.message) for s in results]


@app.post("/stars")
def add_star(star: Star, db: Session = Depends(get_db)):
    """
    Add a new star to the DB. Then push an SSE event.
    """
    new_star = StarDB(x=star.x, y=star.y, message=star.message)
    db.add(new_star)
    db.commit()
    db.refresh(new_star)
    
    # Push SSE event
    star_event_queue.put_nowait({
        "event": "add",
        "star": {
            "id": new_star.id,
            "x": new_star.x,
            "y": new_star.y,
            "message": new_star.message
        }
    })
    return {"id": new_star.id, "x": new_star.x, "y": new_star.y, "message": new_star.message}


@app.delete("/stars/{star_id}")
def remove_star(star_id: int, db: Session = Depends(get_db)):
    """
    Remove a star by ID. Then push an SSE event.
    """
    star_to_remove = db.query(StarDB).filter(StarDB.id == star_id).first()
    if not star_to_remove:
        raise HTTPException(status_code=404, detail="Star not found")

    db.delete(star_to_remove)
    db.commit()
    
    # SSE event
    star_event_queue.put_nowait({
        "event": "remove",
        "star": {
            "id": star_to_remove.id,
            "x": star_to_remove.x,
            "y": star_to_remove.y,
            "message": star_to_remove.message
        }
    })

    return {
        "id": star_to_remove.id,
        "x": star_to_remove.x,
        "y": star_to_remove.y,
        "message": star_to_remove.message
    }

# NB!!! This is dangerous. Only for admins TODO
@app.delete("/stars")
def remove_all_stars(db: Session = Depends(get_db)):
    """
    Remove all stars from the DB.
    """
    db.query(StarDB).delete()
    db.commit()

    # Push SSE event
    star_event_queue.put_nowait({
        "event": "remove_all"
    })

    return {"message": "All stars removed"}


@app.get("/stars/stream")
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
                # We'll yield the event as a Python dict string. 
                yield f"data: {event}\n\n"
            except asyncio.TimeoutError:
                # Keep-alive
                yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

'''

##############################################################################
# 7) To run locally:
#     uvicorn database_service:app --host 127.0.0.1 --port 5000 --reload
##############################################################################