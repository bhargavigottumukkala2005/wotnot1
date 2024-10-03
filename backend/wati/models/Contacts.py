from ..database import database
from sqlalchemy import Integer,Column,String,ARRAY,TIMESTAMP,func,ForeignKey
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy import JSON
from . import User
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from . import User
from sqlalchemy.dialects.postgresql import JSONB

   
# Contact model
# Contact model
class Contact(database.Base):
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(User.User.id))  # Ensure this is correctly linked
    name = Column(String, index=True)
    email = Column(String, index=True)
    phone = Column(String, unique=True, index=True)  # Ensure phone is unique
    tags = Column(MutableList.as_mutable(JSONB), default=[])
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    chats = relationship("Chat", back_populates="contact")

