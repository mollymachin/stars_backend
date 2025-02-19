from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio

from sqlalchemy import create_engine, Column, Integer, Float, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

##############################################################################
# 1) Database Setup (SQLite + SQLAlchemy)
##############################################################################
DB_URL = "sqlite:///./stars.db"  # local file named "stars.db"
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

##############################################################################
# 2) SSE Event Queue
##############################################################################
star_event_queue = asyncio.Queue()

##############################################################################
# 3) FastAPI App
##############################################################################
app = FastAPI()

# Pydantic model for incoming/outgoing star data
class Star(BaseModel):
    id: Optional[int] = None
    x: float
    y: float
    message: str

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

##############################################################################
# 5) Dependency for DB session
##############################################################################
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
    Add a new star to the DB. Then push an SSE event with minimal info.
    """
    new_star = StarDB(x=star.x, y=star.y, message=star.message)
    db.add(new_star)
    db.commit()
    db.refresh(new_star)
    
    # Push SSE event with only minimal data (no message)
    star_event_queue.put_nowait({
        "event": "add",
        "star": {
            "id": new_star.id,
            "x": new_star.x,
            "y": new_star.y
        }
    })
    return {"id": new_star.id, "x": new_star.x, "y": new_star.y, "message": new_star.message}


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


@app.get("/stars/{star_id}")
def get_star(star_id: int, db: Session = Depends(get_db)):
    """
    Retrieve full star details (including message) for a given star ID.
    """
    star = db.query(StarDB).filter(StarDB.id == star_id).first()
    if not star:
        raise HTTPException(status_code=404, detail="Star not found")
    return {"id": star.id, "x": star.x, "y": star.y, "message": star.message}



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




##############################################################################
# 7) To run locally:
#     uvicorn database_service:app --host 127.0.0.1 --port 5000 --reload
##############################################################################