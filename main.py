from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Anonymous Chat", description="Privacy-first anonymous chat application")

# In-memory storage for chat rooms
chat_rooms: Dict[str, dict] = {}
room_timers: Dict[str, asyncio.Task] = {}

# Models
class RoomCreate(BaseModel):
    password: Optional[str] = None

class RoomJoin(BaseModel):
    password: Optional[str] = None

class Message(BaseModel):
    content: str
    timestamp: str
    user_id: str

class ChatRoom:
    def __init__(self, room_id: str, password: Optional[str] = None):
        self.room_id = room_id
        self.password_hash = self._hash_password(password) if password else None
        self.connections: List[WebSocket] = []
        self.messages: List[dict] = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.user_count = 0
        
    def _hash_password(self, password: str) -> str:
        """Hash password with salt"""
        salt = secrets.token_hex(16)
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() + ':' + salt
    
    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash"""
        if not self.password_hash:
            return True  # No password set
        
        stored_hash, salt = self.password_hash.split(':')
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() == stored_hash
    
    def add_connection(self, websocket: WebSocket):
        self.connections.append(websocket)
        self.user_count += 1
        self.last_activity = datetime.now()
        
    def remove_connection(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)
            self.user_count -= 1
            self.last_activity = datetime.now()
    
    def add_message(self, message: dict):
        self.messages.append(message)
        self.last_activity = datetime.now()
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.connections:
            return
            
        dead_connections = []
        for connection in self.connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to connection: {e}")
                dead_connections.append(connection)
        
        # Remove dead connections
        for dead_conn in dead_connections:
            self.remove_connection(dead_conn)

async def cleanup_room(room_id: str):
    """Remove room and all its data from memory"""
    if room_id in chat_rooms:
        room = chat_rooms[room_id]
        
        # Notify all users that the room is ending
        await room.broadcast({
            "type": "room_ended",
            "message": "Chat room has been terminated"
        })
        
        # Close all connections
        for connection in room.connections[:]:
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        # Remove from memory
        del chat_rooms[room_id]
        
        # Cancel timer if exists
        if room_id in room_timers:
            room_timers[room_id].cancel()
            del room_timers[room_id]
            
        logger.info(f"Room {room_id} has been completely destroyed")

async def inactivity_timer(room_id: str, timeout_minutes: int = 30):
    """Auto-destroy room after inactivity"""
    try:
        await asyncio.sleep(timeout_minutes * 60)  # Convert to seconds
        if room_id in chat_rooms:
            logger.info(f"Room {room_id} timed out due to inactivity")
            await cleanup_room(room_id)
    except asyncio.CancelledError:
        pass

def reset_inactivity_timer(room_id: str):
    """Reset the inactivity timer for a room"""
    if room_id in room_timers:
        room_timers[room_id].cancel()
    
    # Create new timer
    timer = asyncio.create_task(inactivity_timer(room_id))
    room_timers[room_id] = timer

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def homepage():
    """Serve the homepage"""
    try:
        with open("static/index.html", "r") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Anonymous Chat</title></head>
        <body>
            <h1>Anonymous Chat</h1>
            <p>Static files not found. Please ensure static/index.html exists.</p>
        </body>
        </html>
        """)

@app.get("/room/{room_id}", response_class=HTMLResponse)
async def chat_room(room_id: str):
    """Serve the chat room page"""
    try:
        with open("static/room.html", "r") as f:
            content = f.read()
            # Inject room_id into the HTML
            content = content.replace("{{ROOM_ID}}", room_id)
            return HTMLResponse(content)
    except FileNotFoundError:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Chat Room</title></head>
        <body>
            <h1>Chat Room: {room_id}</h1>
            <p>Static files not found. Please ensure static/room.html exists.</p>
        </body>
        </html>
        """)

@app.post("/api/create-room")
async def create_room(room_data: RoomCreate):
    """Create a new chat room"""
    room_id = str(uuid.uuid4())[:8]  # 8-character room ID
    
    # Create new room
    room = ChatRoom(room_id, room_data.password)
    chat_rooms[room_id] = room
    
    # Start inactivity timer
    reset_inactivity_timer(room_id)
    
    logger.info(f"Created new room: {room_id}")
    
    return {
        "room_id": room_id,
        "room_url": f"/room/{room_id}",
        "password_protected": room_data.password is not None
    }

@app.post("/api/join-room/{room_id}")
async def join_room(room_id: str, join_data: RoomJoin):
    """Validate room access before WebSocket connection"""
    if room_id not in chat_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = chat_rooms[room_id]
    
    # Check password if required
    if room.password_hash:
        if not join_data.password or not room.verify_password(join_data.password):
            raise HTTPException(status_code=401, detail="Invalid password")
    
    return {
        "success": True,
        "room_id": room_id,
        "user_count": room.user_count
    }

@app.post("/api/end-room/{room_id}")
async def end_room(room_id: str):
    """Manually end a chat room"""
    if room_id not in chat_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    
    await cleanup_room(room_id)
    
    return {"success": True, "message": "Room ended successfully"}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()
    
    # Check if room exists
    if room_id not in chat_rooms:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Room not found"
        }))
        await websocket.close()
        return
    
    room = chat_rooms[room_id]
    user_id = str(uuid.uuid4())[:8]
    
    # Add connection to room
    room.add_connection(websocket)
    reset_inactivity_timer(room_id)
    
    # Send welcome message and chat history
    await websocket.send_text(json.dumps({
        "type": "welcome",
        "user_id": user_id,
        "room_id": room_id,
        "user_count": room.user_count
    }))
    
    # Send chat history
    for message in room.messages:
        await websocket.send_text(json.dumps(message))
    
    # Notify others that someone joined
    await room.broadcast({
        "type": "user_joined",
        "message": f"User {user_id} joined the chat",
        "user_count": room.user_count
    })
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "message":
                # Create message object
                message = {
                    "type": "message",
                    "content": message_data.get("content", ""),
                    "user_id": user_id,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Store message
                room.add_message(message)
                
                # Broadcast to all users
                await room.broadcast(message)
                
                # Reset inactivity timer
                reset_inactivity_timer(room_id)
                
            elif message_data.get("type") == "end_chat":
                # User manually ended the chat
                await cleanup_room(room_id)
                break
                
    except WebSocketDisconnect:
        # Remove connection
        room.remove_connection(websocket)
        
        # Notify others that someone left
        if room_id in chat_rooms:  # Room might have been deleted
            await room.broadcast({
                "type": "user_left",
                "message": f"User {user_id} left the chat",
                "user_count": room.user_count
            })
            
            # If no users left, clean up the room
            if room.user_count == 0:
                await cleanup_room(room_id)
            else:
                reset_inactivity_timer(room_id)
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        room.remove_connection(websocket)
        if room_id in chat_rooms and room.user_count == 0:
            await cleanup_room(room_id)

@app.get("/api/room/{room_id}/status")
async def room_status(room_id: str):
    """Get room status"""
    if room_id not in chat_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = chat_rooms[room_id]
    return {
        "room_id": room_id,
        "user_count": room.user_count,
        "message_count": len(room.messages),
        "created_at": room.created_at.isoformat(),
        "last_activity": room.last_activity.isoformat(),
        "password_protected": room.password_hash is not None
    }

@app.get("/api/stats")
async def get_stats():
    """Get server statistics"""
    return {
        "active_rooms": len(chat_rooms),
        "total_connections": sum(len(room.connections) for room in chat_rooms.values()),
        "total_messages": sum(len(room.messages) for room in chat_rooms.values())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)