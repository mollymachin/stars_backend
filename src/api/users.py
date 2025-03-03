from fastapi import APIRouter, HTTPException, Depends
import logging
from typing import List, Optional

from src.config.settings import settings
from src.models.user import User
from src.db.azure_tables import tables
from src.api.sse_publisher import publish_user_event

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/")
async def create_user(user: User):
    """Create a new user"""
    user_entity = user.to_entity()
    tables["Users"].create_entity(user_entity)
    
    # Use the new publisher module
    try:
        await publish_user_event("create", {
            "id": user_entity["RowKey"],
            "name": user.name,
            "email": user.email
        })
    except Exception as e:
        logger.warning(f"Failed to publish event for new user: {str(e)}")
    
    return {"user_id": user_entity["RowKey"], **user.model_dump()}

@router.get("/")
async def get_users():
    """Get all users"""
    users = []
    try:
        for user_entity in tables["Users"].query_entities(query_filter="PartitionKey eq 'USER'"):
            users.append({
                "id": user_entity["RowKey"],
                "name": user_entity["Username"],
                "email": user_entity["Email"],
                "created_at": user_entity.get("CreatedAt")
            })
        return users
    except Exception as e:
        logger.error(f"Error retrieving users: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving users")

@router.get("/{user_id}")
async def get_user(user_id: str):
    """Get a specific user by ID"""
    try:
        user_entity = tables["Users"].get_entity(partition_key="USER", row_key=user_id)
        return {
            "id": user_entity["RowKey"],
            "name": user_entity["Username"],
            "email": user_entity["Email"],
            "created_at": user_entity.get("CreatedAt")
        }
    except Exception as e:
        logger.error(f"Error retrieving user {user_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="User not found")

@router.put("/{user_id}")
async def update_user(user_id: str, user: User):
    """Update a user's information"""
    try:
        # Get existing user to ensure it exists
        existing_user = tables["Users"].get_entity(partition_key="USER", row_key=user_id)
        
        # Update fields
        existing_user["Username"] = user.name
        existing_user["Email"] = user.email
        
        # Save changes
        tables["Users"].update_entity(existing_user)
        
        # Use the new publisher module
        try:
            await publish_user_event("update", {
                "id": user_id,
                "name": user.name,
                "email": user.email
            })
        except Exception as e:
            logger.warning(f"Failed to publish event for updated user: {str(e)}")
            
        return {
            "id": user_id,
            "name": user.name,
            "email": user.email,
            "created_at": existing_user.get("CreatedAt")
        }
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="User not found")

@router.delete("/{user_id}")
async def delete_user(user_id: str):
    """Delete a user"""
    try:
        # Get existing user to ensure it exists
        existing_user = tables["Users"].get_entity(partition_key="USER", row_key=user_id)
        
        # Delete the user
        tables["Users"].delete_entity(partition_key="USER", row_key=user_id)
        
        # Use the new publisher module
        try:
            await publish_user_event("delete", {
                "id": user_id
            })
        except Exception as e:
            logger.warning(f"Failed to publish event for deleted user: {str(e)}")
            
        return {"id": user_id, "status": "deleted"}
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="User not found")

@router.get("/{user_id}/stars")
async def get_user_stars(user_id: str):
    """Get all stars created by a specific user"""
    try:
        # Ensure user exists
        tables["Users"].get_entity(partition_key="USER", row_key=user_id)
        
        # Get user's stars
        user_stars = []
        # In a real implementation, this would query a relation table or filter stars by user
        # For now, this is a placeholder
        
        return user_stars
    except Exception as e:
        logger.error(f"Error retrieving stars for user {user_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="User not found")
