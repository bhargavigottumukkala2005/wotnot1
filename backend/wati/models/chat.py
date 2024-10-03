from ..database import database
from sqlalchemy import Integer, Column, String, TIMESTAMP, func, ForeignKey
from sqlalchemy.orm import relationship

class Chat(database.Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("Users.id"))  # Ensure the casing matches the Users table
    contact_id = Column(Integer, ForeignKey("contacts.id"))  # Ensure this matches the contacts table
    latest_message = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="chats")  # Many-to-one relationship
    contact = relationship("Contact", back_populates="chats")







#class BroadcastAnalysis(database.Base):
  #  __tablename__ = "BroadcastAnalysis"
    
    #id = Column(Integer, primary_key=True, index=True)
   # user_id = Column(Integer, ForeignKey('User.id'))  # Assuming User model exists
   # broadcast_id = Column(Integer, ForeignKey('BroadcastList.id'))  # Assuming BroadcastList model exists
   # status = Column(String)
   # message_id = Column(String, unique=True)
   # phone_no = Column(String)
   # contact_name = Column(String)
   # read = Column(Boolean, nullable=True)
   # delivered = Column(Boolean, nullable=True)
   # sent = Column(Boolean, nullable=True)
   # replied = Column(Boolean, nullable=True)
   # last_message_time = Column(datetime)  # Track the last message time
