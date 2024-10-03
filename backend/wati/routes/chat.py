from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from typing import List
from ..database import database  # Adjust the import path as necessary
from ..models import chat, Broadcast,Contacts  # Ensure correct import paths
from pydantic import BaseModel
from datetime import datetime,timedelta

# Define response models
class ContactDetails(BaseModel):
    name: str
    email: str
    phone: str

class ChatResponse(BaseModel):
    message_id: str
    status: str
    contact_details: ContactDetails

    class Config:
        orm_mode = True

router = APIRouter(tags=['chat'])

# Helper function to determine if a chat is active
def is_active(last_active_time):
    """Check if the last active time is within the last 24 hours."""
    if last_active_time is None:
        return False
    current_time = datetime.utcnow()  # Current UTC time
    return (current_time - last_active_time) < timedelta(days=1)

@router.get("/active-chats", response_model=List[ChatResponse])
async def get_active_chats(db: AsyncSession = Depends(database.get_db)):
    try:
        async with db() as session:
            # Query to fetch chats and check activity status based on last active time
            query = (
                select(chat.Chat)
                .options(joinedload(chat.contact))  # Load related contact data
            )

            result = await session.execute(query)  # Execute the query
            chats_data = result.scalars().all()  # Get all chats

            chats = []
            for chat in chats_data:
                # Query BroadcastAnalysis for last active time
                broadcast_analysis = (
                    await session.execute(
                        select(Broadcast.BroadcastAnalysis)
                        .where(Broadcast.BroadcastAnalysis.message_id == chat.latest_message)
                    )
                )
                broadcast_analysis = broadcast_analysis.scalars().first()

                if broadcast_analysis:
                    active_status = is_active(broadcast_analysis.last_active_time)
                    status = "active" if active_status else "inactive"

                    chats.append({
                        "message_id": chat.latest_message,
                        "status": status,
                        "contact_details": {
                            "name": chat.contact.name,
                            "email": chat.contact.email,
                            "phone": chat.contact.phone
                        } if chat.contact else None
                    })

            return chats  # Return the list of chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

'''from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..models.chat import BroadcastAnalysis
from ..database import get_db
from ..Schemas.chat import BroadcastAnalysisCreate, BroadcastAnalysisResponse
from datetime import datetime, timedelta
import logging
from starlette.responses import PlainTextResponse

router = APIRouter()

WEBHOOK_VERIFY_TOKEN = "12345"  # Replace with your verification token

# Meta Webhook verification endpoint
@router.get("/meta-webhook")
async def verify_webhook(request: Request):
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    hubmode = request.query_params.get("hub.mode")
    print(f"Received verify_token: {challenge}, Expected: {WEBHOOK_VERIFY_TOKEN}")
    if verify_token == WEBHOOK_VERIFY_TOKEN and hubmode == "subscribe":
        return PlainTextResponse(content=request.query_params.get("hub.challenge"), status_code=200)
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")

# Webhook event listener to receive message status updates
@router.post("/meta-webhook")
async def receive_meta_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
        print(body)

        if "entry" not in body:
            raise HTTPException(status_code=400, detail="Invalid webhook format")

        for event in body["entry"]:
            if "changes" not in event:
                raise HTTPException(status_code=400, detail="Missing 'changes' key in entry")

            for change in event["changes"]:
                if "value" not in change:
                    raise HTTPException(status_code=400, detail="Missing 'value' key in changes")

                value = change["value"]

                if "statuses" in value:
                    for status in value["statuses"]:
                        message_status = status["status"]
                        wamid = status['id']
                        timestamp = status['timestamp']

                        last_message_time = datetime.fromtimestamp(int(timestamp))

                        broadcast_report = (
                            db.query(BroadcastAnalysis)
                            .filter(BroadcastAnalysis.message_id == wamid)
                            .first()
                        )

                        if not broadcast_report:
                            raise HTTPException(status_code=404, detail="Broadcast not found")

                        broadcast_report.read = (message_status == "read")
                        broadcast_report.delivered = (message_status == "delivered")
                        broadcast_report.sent = (message_status == "sent")
                        broadcast_report.last_message_time = last_message_time  # Update last message time
                        broadcast_report.status = message_status

                        db.add(broadcast_report)
                        db.commit()
                        db.refresh(broadcast_report)

                elif "messages" in value:
                    for message in value["messages"]:
                        message_reply = True
                        message_status = 'replied'
                        wamid = message['context']['id']

                        broadcast_report = (
                            db.query(BroadcastAnalysis)
                            .filter(BroadcastAnalysis.message_id == wamid)
                            .first()
                        )

                        if not broadcast_report:
                            raise HTTPException(status_code=404, detail="Broadcast not found")

                        broadcast_report.replied = message_reply
                        broadcast_report.status = message_status
                        broadcast_report.last_message_time = datetime.utcnow()  # Assuming current time for replies

                        db.add(broadcast_report)
                        db.commit()
                        db.refresh(broadcast_report)

        return {"status": "ok"}

    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# New endpoint to check if the chat is active
@router.get("/is-chat-active/{wamid}", response_model=dict)
async def is_chat_active(wamid: str, db: Session = Depends(get_db)):
    broadcast_entry = db.query(BroadcastAnalysis).filter(BroadcastAnalysis.message_id == wamid).first()

    if not broadcast_entry:
        raise HTTPException(status_code=404, detail="Chat not found")

    ACTIVE_CHAT_DURATION = timedelta(hours=24)

    if broadcast_entry.last_message_time and (datetime.utcnow() - broadcast_entry.last_message_time) <= ACTIVE_CHAT_DURATION:
        return {"status": "active"}
    else:
        return {"status": "inactive"}'''
