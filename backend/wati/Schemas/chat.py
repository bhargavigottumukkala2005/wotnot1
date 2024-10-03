from pydantic import BaseModel
from typing import Optional, Dict

class ContactDetails(BaseModel):
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]

class ChatResponse(BaseModel):
    message_id: str
    status: str
    latest_message: str
    is_active: bool
    contact_details: Optional[ContactDetails]

    class Config:
        orm_mode = True  # Ensure Pydantic can work with SQLAlchemy objects
class MessageResponse(BaseModel):
    message_id: str
    status: str
    latest_message: str
    is_active: bool
    contact_details: dict
    
class MessageRequest(BaseModel):
    chat_id: int
    message: str
    phone_number: str  # Add phone number

    class Config:
        from_attributes = True

'''from pydantic import BaseModel
from typing import Optional

class ContactDetails(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

class MessageResponse(BaseModel):
    message_id: str
    status: str
    latest_message: Optional[str] = None
    is_active: bool
    contact_details: Optional[ContactDetails] = None  '''