import uuid
from typing import Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, EmailStr

class User(BaseModel):
    """User model representing a user of the application"""
    id: Optional[str] = None
    name: str
    email: str
    created_at: Optional[datetime] = None
    
    @field_validator('name')
    def validate_name(cls, v):
        if len(v) < 2:
            raise ValueError('Name must be at least 2 characters')
        return v
    
    def to_entity(self):
        """Convert the User model to an Azure Table entity"""
        return {
            "PartitionKey": "USER",
            "RowKey": self.id or str(uuid.uuid4()),
            "Username": self.name,
            "Email": self.email,
            "CreatedAt": datetime.now().isoformat()
        }
    
    @classmethod
    def from_entity(cls, entity: Dict) -> "User":
        """Create user model from Azure table entity"""
        return cls(
            id=entity["RowKey"],
            name=entity["Username"],
            email=entity["Email"],
            created_at=entity.get("CreatedAt")
        )
