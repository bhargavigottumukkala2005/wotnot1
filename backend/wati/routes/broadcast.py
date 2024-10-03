from fastapi import APIRouter,Depends,HTTPException, File, UploadFile,Request
from ..models import Broadcast,Contacts,User,chat
from ..Schemas import broadcast,user,chat
from ..database import database
from sqlalchemy.orm import Session,joinedload
from datetime import datetime,timedelta
 # Import your models
from ..database import database
from pydantic import BaseModel
import requests
import json
from fastapi.responses import JSONResponse
import csv
import io
from ..oauth2 import get_current_user
from dramatiq import get_broker
import asyncio
from twilio.rest import Client

from ..crud.template import send_template_to_whatsapp

from fastapi import APIRouter,Depends,HTTPException, File, UploadFile,Request
from starlette.responses import PlainTextResponse
from ..oauth2 import get_current_user
from ..crud.template import send_template_to_whatsapp# Replace with your actual WhatsApp Business API endpoint and token
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text



# Replace with your actual WhatsApp Business API endpoint and token


router=APIRouter( tags=['Broadcast'])

WEBHOOK_VERIFY_TOKEN = "56789"  # Replace with your verification token

# Meta Webhook verification endpoint
@router.get("/meta-webhook")
async def verify_webhook(request: Request):
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    hubmode = request.query_params.get("hub.mode")
    print(f"Received verify_token: {challenge}, Expected: {WEBHOOK_VERIFY_TOKEN}")
    if verify_token == WEBHOOK_VERIFY_TOKEN and hubmode == "subscribe" :
        return PlainTextResponse(content=request.query_params.get("hub.challenge"),status_code=200)
    
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    
# Webhook event listener to receive message status updates


def is_active(last_active_time):
    """ Check if the last active time is within the last 24 hours. """
    if last_active_time is None:
        return False
    # Check if the last active time is less than 24 hours from now
    return (datetime.utcnow() + timedelta(hours=5, minutes=30) - last_active_time) < timedelta(days=1)

@router.post("/meta-webhook")
async def receive_meta_webhook(request: Request, db: Session = Depends(database.get_db)):
    try:
        body = await request.json()
        
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
                        if "recipient_id" not in status or "id" not in status or "status" not in status or "timestamp" not in status:
                            raise HTTPException(status_code=400, detail="Missing keys in statuses")

                        message_status = status["status"]
                        wamid = status['id']

                        message_read = message_delivered = message_sent = False

                        if message_status == "read":
                            message_read = True
                            message_delivered = True
                            message_sent = True
                        elif message_status == "delivered":
                            message_delivered = True
                            message_sent = True
                        elif message_status == "sent":
                            message_sent = True

                        broadcast_report = (
                            db.query(Broadcast.BroadcastAnalysis)
                            .filter(Broadcast.BroadcastAnalysis.message_id == wamid)
                            .first()
                        )
                        
                        if not broadcast_report:
                            raise HTTPException(status_code=404, detail="Broadcast not found")

                        if wamid:
                            broadcast_report.read = message_read
                            broadcast_report.delivered = message_delivered
                            broadcast_report.sent = message_sent
                            broadcast_report.status = message_status
                            # Update last active time in IST
                            broadcast_report.last_active_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
                            # Set active status based on last active time
                            broadcast_report.active = is_active(broadcast_report.last_active_time)

                        db.add(broadcast_report)
                        db.commit()
                        db.refresh(broadcast_report) 
                
                elif "messages" in value:
                    for message in value["messages"]:
                        message_reply = True
                        message_status = 'replied'
                         
                        wamid = message['context']['id']
                        broadcast_report = (
                            db.query(Broadcast.BroadcastAnalysis)
                            .filter(Broadcast.BroadcastAnalysis.message_id == wamid)
                            .first()
                        )
                        
                        if not broadcast_report:
                            raise HTTPException(status_code=404, detail="Broadcast not found")

                        if wamid:
                            broadcast_report.replied = message_sent = message_reply
                            broadcast_report.status = message_status
                            # Update last active time in IST
                            broadcast_report.last_active_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
                            # Set active status based on last active time
                            broadcast_report.active = is_active(broadcast_report.last_active_time)

                        db.add(broadcast_report)
                        db.commit()
                        db.refresh(broadcast_report) 

        return {"status": "ok"}

    except KeyError as e:
        logging.error(f"Missing key in webhook payload: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Missing key: {str(e)}")
    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

def normalize_contacts_phone_numbers(db: Session):
    # Update query to remove both '+' and spaces from phone numbers
    db.execute(text("UPDATE contacts SET phone = REPLACE(REPLACE(phone, '+', ''), ' ', '')"))
    db.commit()

@router.get("/api/chats", response_model=list[chat.ChatResponse])
async def get_active_chats(db: Session = Depends(database.get_db)):
    try:
        # Query to get active broadcasts along with associated contacts
        active_broadcasts = (
            db.query(Broadcast.BroadcastAnalysis)
            .filter(Broadcast.BroadcastAnalysis.active == True)
            .options(joinedload(Broadcast.BroadcastAnalysis.contact))  # Eager load contact data
            .all()
        )

        # Debugging output
        print("Active broadcasts fetched from DB:", active_broadcasts)

        chats = []
        for broadcast in active_broadcasts:
            contact_details = {
                "name": broadcast.contact.name if broadcast.contact else "Unknown",
                "email": broadcast.contact.email if broadcast.contact and broadcast.contact.email else "No email available",
                "phone": broadcast.contact.phone if broadcast.contact and broadcast.contact.phone else "No phone available"
            }

            latest_message = f"Message sent to {contact_details['name']}"

            chats.append({
                "message_id": broadcast.message_id,
                "status": broadcast.status,
                "latest_message": latest_message,
                "is_active": True,
                "contact_details": contact_details
            })

        return chats
    except Exception as e:
        print("Error fetching active chats:", str(e))  # Additional error logging
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-chats", response_model=list[chat.ChatResponse])
async def active_chats(db: Session = Depends(database.get_db)):
    return await get_active_chats(db)  # Await the coroutine properly



# Function to send message via Twilio
def send_sms(to_number, message):
    account_sid = 'your_twilio_account_sid'
    auth_token = 'your_twilio_auth_token'
    twilio_number = 'your_twilio_phone_number'

    client = Client(account_sid, auth_token)
    client.messages.create(
        body=message,
        from_=twilio_number,
        to=to_number
    )

@router.post("/api/send-message")
async def send_message(
    message_request: chat.MessageRequest, 
    db: Session = Depends(database.get_db), 
    current_user: User.User = Depends(get_current_user)
):
    # Validate chat existence
    chat = db.query(chat.Chat).filter(chat.Chat.message_id == message_request.chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Validate user permission
    if chat.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Create new message
    new_message = chat.Message(
        chat_id=message_request.chat_id,
        text=message_request.message,
        sender_id=current_user.id
    )

    # Add message to database
    db.add(new_message)
    db.commit()

    # Update latest message in chat
    chat.latest_message = message_request.message
    db.commit()

    # Send message to phone number using Twilio
    try:
        send_sms(message_request.phone_number, message_request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending SMS: {str(e)}")

    return {"message": "Message sent successfully"}
# Broadcast 2 routes

# test

# @router.post("/send-template-message/")
# async def send_template_message(
#     request: broadcast.input_broadcast, 
#     get_current_user: user.newuser = Depends(get_current_user), 
#     db: Session = Depends(database.get_db)
# ):
#     print(request)

#     # Save broadcast details
#     broadcastList = Broadcast.BroadcastList(
#         user_id=get_current_user.id,
#         name=request.name,
#         template=request.template,
#         contacts=request.recipients,
#         type=request.type,
#         success=0,
#         failed=0,
#         status="processing..."
#     )
#     db.add(broadcastList)
#     db.commit()
#     db.refresh(broadcastList)
    
#     saved_broadcast_id = broadcastList.id


#     # Prepare API URL and headers
#     API_url = f"https://graph.facebook.com/v20.0/{get_current_user.Phone_id}/messages"
#     headers = {
#         "Authorization": f"Bearer {get_current_user.PAccessToken}",
#         "Content-Type": "application/json"
#     }

#     success_count = 0
#     errors = []
#     failed_count = 0

#     for recipient in request.recipients:
#         # Create the base payload
#         data = {
#             "messaging_product": "whatsapp",
#             "to": recipient,
#             "type": "template",
#             "template": {
#                 "name": request.template,
#                 "language": {"code": "en_US"}
#             }
#         }

#         # Check if the image URL is provided and add it to the payload
#         if request.image_id:
#             data["template"]["components"] = [
#                 {
#                     "type": "header",
#                     "parameters": [
#                         {
#                             "type": "image",
#                             "image": {
#                                         "id": request.image_id
#                         }
#                         }
#                     ]
#                 }
#             ]

#         # Check if body parameters are provided and add them to the payload
#         # if request.body_parameters:
#         #     body_params = [{"type": "text", "text": param} for param in request.body_parameters]
#         #     if "components" not in data["template"]:
#         #         data["template"]["components"] = []
#         #     data["template"]["components"].append({
#         #         "type": "body",
#         #         "parameters": body_params
#         #     })

#         # Send the request to the WhatsApp API
#         response = requests.post(API_url, headers=headers, data=json.dumps(data))
#         response_data = response.json()

#         if response.status_code == 200:
#             success_count += 1
#             wamid = response_data['messages'][0]['id']
#             phone_num = response_data['contacts'][0]["wa_id"]

#             MessageIdLog = Broadcast.BroadcastAnalysis(
#                 user_id=get_current_user.id,
#                 broadcast_id=saved_broadcast_id,
#                 message_id=wamid,
#                 status="sent",
#                 phone_no=phone_num,
#             )
#             db.add(MessageIdLog)
#             db.commit()
#             db.refresh(MessageIdLog)
#         else:
#             failed_count += 1
#             errors.append({"recipient": recipient, "error": response_data})

#             MessageIdLog = Broadcast.BroadcastAnalysis(
#                 user_id=get_current_user.id,
#                 broadcast_id=saved_broadcast_id,
#                 status="failed",
#                 phone_no=recipient,
#             )
#             db.add(MessageIdLog)
#             db.commit()
#             db.refresh(MessageIdLog)

#     # Update broadcast status
#     broadcast = db.query(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.id == saved_broadcast_id).first()
#     if not broadcast:
#         raise HTTPException(status_code=404, detail="Broadcast not found")

#     if saved_broadcast_id:
#         broadcast.success = success_count
#         broadcast.status = "Successful" if failed_count == 0 else "Partially Successful"
#         broadcast.failed = failed_count
#     db.add(broadcast)
#     db.commit()
#     db.refresh(broadcast)

#     return {
#         "status": "completed",
#         "successful_messages": success_count,
#         "errors": errors
#     }


@router.post("/send-template-message/")
async def send_template_message(
    request: broadcast.input_broadcast,
    get_current_user: user.newuser = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    # Save broadcast details
    broadcastList = Broadcast.BroadcastList(
        user_id=get_current_user.id,
        name=request.name,
        template=request.template,
        contacts=[contact.phone for contact in request.recipients],  # Only storing phone numbers for now
        type=request.type,
        success=0,
        failed=0,
        status="processing..."
    )
    db.add(broadcastList)
    db.commit()
    db.refresh(broadcastList)

    saved_broadcast_id = broadcastList.id

    API_url = f"https://graph.facebook.com/v20.0/{get_current_user.Phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {get_current_user.PAccessToken}",
        "Content-Type": "application/json"
    }

    success_count = 0
    errors = []
    failed_count = 0

    for contact in request.recipients:
        recipient_name = contact.name
        recipient_phone = contact.phone

        data = {
            "messaging_product": "whatsapp",
            "to": recipient_phone,
            "type": "template",
            "template": {
                "name": request.template,
                "language": {"code": "en_US"},
                # You can insert recipient_name into your message template if needed
            }
        }

        if request.image_id:
            data["template"]["components"] = [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "image",
                            "image": {"id": request.image_id}
                        }
                    ]
                }
            ]

        
        
        if request.body_parameters:
            if request.body_parameters == "Name":
                body_params = [{"type": "text","text": f"{recipient_name}"}]
                
            else:
                data["template"]["components"] = []

            if "components" not in data["template"]:
                data["template"]["components"] = []
            data["template"]["components"].append({
                "type": "body",
                "parameters": body_params
            })

        

        response = requests.post(API_url, headers=headers, data=json.dumps(data))
        response_data = response.json()

        if response.status_code == 200:
            success_count += 1
            wamid = response_data['messages'][0]['id']
            phone_num = response_data['contacts'][0]["wa_id"]

            MessageIdLog = Broadcast.BroadcastAnalysis(
                user_id=get_current_user.id,
                broadcast_id=saved_broadcast_id,
                message_id=wamid,
                status="sent",
                phone_no=phone_num,
                contact_name=recipient_name,
            )
            db.add(MessageIdLog)
            db.commit()
            db.refresh(MessageIdLog)
        else:
            failed_count += 1
            errors.append({"recipient": recipient_phone, "error": response_data})

            MessageIdLog = Broadcast.BroadcastAnalysis(
                user_id=get_current_user.id,
                broadcast_id=saved_broadcast_id,
                status="failed",
                phone_no=recipient_phone,
                contact_name=recipient_name,
            )
            db.add(MessageIdLog)
            db.commit()
            db.refresh(MessageIdLog)

    # Update broadcast status
    broadcast = db.query(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.id == saved_broadcast_id).first()
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    broadcast.success = success_count
    broadcast.status = "Successful" if failed_count == 0 else "Partially Successful"
    broadcast.failed = failed_count
    db.add(broadcast)
    db.commit()
    db.refresh(broadcast)

    return {
        "status": "completed",
        "successful_messages": success_count,
        "errors": errors
    }





# route for fetchlist in Broadcast template
@router.get("/templates")
def get_templates(get_current_user: user.newuser=Depends(get_current_user)):

    API_URL = f'https://graph.facebook.com/v15.0/{get_current_user.WABAID}/message_templates'
    headers = {
        'Authorization': f'Bearer {get_current_user.PAccessToken}'
    }

    response = requests.get(API_URL, headers=headers)
    
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    # Extract template names
    template_names = [template['name'] for template in data.get('data', [])]
    return JSONResponse(content=template_names)

# Route to create add broadcast in the list 
@router.post("/broadcast")
def broadcastList(request:broadcast.BroadcastListCreate,db: Session = Depends(database.get_db),get_current_user: user.newuser=Depends(get_current_user)):
    broadcastList=Broadcast.BroadcastList(
        user_id=get_current_user.id,
        name=request.name,
        template=request.template,
        contacts=request.contacts,
        type=request.type,
        success=request.success,
        failed=request.failed,
        status=request.status,
        scheduled_time=request.scheduled_time,
        task_id=request.task_id
    )
    db.add(broadcastList)
    db.commit()
    db.refresh(broadcastList)
    return{
        "broadcast_id":broadcastList.id
    } 

# Route to fetch the broadcastlist
@router.get('/broadcast')
def fetchbroadcastList(skip: int = 0, limit: int = 10, tag: str = None, db: Session = Depends(database.get_db),
                      get_current_user: user.newuser=Depends(get_current_user) ):
    broadcastList=db.query(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.user_id==get_current_user.id).order_by(Broadcast.BroadcastList.id.desc()).all()
    return broadcastList
# Put route for the broadcastlist (rightnow primaryly used for updating the task_id )
@router.put("/broadcast/{broadcast_id}")
async def update_broadcast(broadcast_id: int, broadcast_update: broadcast.BroadcastListUpdate, db: Session = Depends(database.get_db),get_current_user: user.newuser=Depends(get_current_user)):
    # Retrieve the broadcast entry from the database
    broadcast = db.query(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.id == broadcast_id).first()

    # If the broadcast entry does not exist, raise an HTTP 404 error
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    # Update the broadcast entry with new data
    if broadcast_update.task_id:
        broadcast.task_id = broadcast_update.task_id

    # Commit the changes to the database
    db.add(broadcast)
    db.commit()
    db.refresh(broadcast)

    # Return the updated broadcast entry
    return {"message": "Broadcast updated successfully", "broadcast_id": broadcast_id, "task_id": broadcast.task_id}


# Route to fetch the scheduled broadcastlist
@router.get("/scheduled-broadcast")
def fetchScheduledbroadcastList(skip: int = 0, limit: int = 10, tag: str = None, db: Session = Depends(database.get_db),
                      get_current_user: user.newuser=Depends(get_current_user) ):
    ScheduledbroadcastList=db.query(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.status=="Scheduled").order_by(Broadcast.BroadcastList.id.desc()).all()
    return ScheduledbroadcastList

# Route to CSV import contacts in the broadcast form
@router.post("/import-contacts")
def import_contacts(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    contents = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(contents))

    contacts = []
    for row in reader:
        contact = Contacts.Contact(name=row['name'], phone=row['phone'])
        contacts.append(contact)
       

    return {"contacts": contacts}
   
# Broadcast 1 routes

@router.get("/template")
def get_templates( get_current_user: user.newuser=Depends(get_current_user)):

    API_URL = f'https://graph.facebook.com/v15.0/{get_current_user.WABAID}/message_templates'
    headers = {
        'Authorization': f'Bearer {get_current_user.PAccessToken}'
    }

    response = requests.get(API_URL, headers=headers)
    
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()

    return data


@router.delete("/broadcasts-delete/{broadcast_id}")
async def delete_scheduled_broadcast(broadcast_id: str, db: Session = Depends(database.get_db),get_current_user: user.newuser=Depends(get_current_user)):
    # Fetch the broadcast
    broadcast = db.query(Broadcast.BroadcastList).filter(Broadcast.BroadcastList.id==broadcast_id).first()
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    
    # Update the status to 'canceled'
    broadcast.status = "Cancelled"
    db.commit()
    
    return {"detail": "Scheduled broadcast has been canceled."}



import logging

@router.post("/create-template", response_model=broadcast.TemplateResponse)
async def create_template(template: broadcast.TemplateCreate , request : Request , get_current_user: user.newuser=Depends(get_current_user)):
    try:
        template = await request.json()
        broadcast.TemplateCreate.validate_template(template)
        response = await send_template_to_whatsapp(template , get_current_user.PAccessToken , get_current_user.WABAID )
        return response
    except HTTPException as e:
        logging.critical(e)
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    

@router.get("/broadcast-report/{broadcast_id}")
def BroadcastReport(broadcast_id:int,get_current_user: user.newuser=Depends(get_current_user),db: Session = Depends(database.get_db)):

    broadcast_data=db.query(Broadcast.BroadcastAnalysis).filter((Broadcast.BroadcastAnalysis.user_id==get_current_user.id) &(Broadcast.BroadcastAnalysis.broadcast_id==broadcast_id)).all()

    if not broadcast_data:
        raise HTTPException(status_code=404,detail="Broadcast data not found")

    return broadcast_data

@router.post("/upload-media")
async def upload_file(file: UploadFile = File(...),get_current_user: user.newuser=Depends(get_current_user)):
    # Read the contents of the uploaded file
    contents = await file.read()
    

    # Upload the file to WhatsApp directly from memory (no need to save it)
    try:
        media_url = f"https://graph.facebook.com/v20.0/{get_current_user.Phone_id}/media"
        headers = {
            "Authorization": f"Bearer {get_current_user.PAccessToken}"
        }
        files = {
            'file': (file.filename, contents, file.content_type),  # File from memory
        }
        data = {
            'type': file.content_type.split("/")[0],
            'messaging_product': 'whatsapp' # Extract media type (image, video, etc.)
        }

        # Make the POST request to upload media to WhatsApp
        response = requests.post(media_url, headers=headers, files=files, data=data)

        # Check for errors in the WhatsApp API response
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.json())

        # Get the media ID from the response
        media_id = response.json().get("id")

        return JSONResponse(content={
            "filename": file.filename,
            "file_size": len(contents),
            "content_type": file.content_type,
            "whatsapp_media_id": media_id
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading file to WhatsApp: {str(e)}")

