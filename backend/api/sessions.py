from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import secrets
import json

from services.database import get_session, Session, Device, User
from services.webrtc_server import WebRTCManager

router = APIRouter()
webrtc_manager = WebRTCManager()


# Pydantic schemas
class SessionCreate(BaseModel):
    user_id: int
    device_id: int


class SessionResponse(BaseModel):
    id: int
    user_id: int
    device_id: int
    session_token: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    data_transferred: float

    class Config:
        from_attributes = True


@router.post("/", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: SessionCreate, db: AsyncSession = Depends(get_session)
):
    """Create a new streaming session"""
    # Verify user exists
    stmt = select(User).where(User.id == session_data.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found or inactive"
        )

    # Verify device exists and belongs to user
    stmt = select(Device).where(Device.id == session_data.device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )

    if device.user_id != session_data.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device does not belong to user",
        )

    if device.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device is not running. Please start the device first.",
        )

    # Generate session token
    session_token = secrets.token_urlsafe(32)

    # Create session
    new_session = Session(
        user_id=session_data.user_id,
        device_id=session_data.device_id,
        session_token=session_token,
        status="active",
    )

    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    return new_session


@router.get("/", response_model=List[SessionResponse])
async def list_sessions(
    user_id: Optional[int] = None,
    active_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_session),
):
    """List all sessions"""
    stmt = select(Session)

    if user_id:
        stmt = stmt.where(Session.user_id == user_id)

    if active_only:
        stmt = stmt.where(Session.status == "active")

    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return sessions


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int, db: AsyncSession = Depends(get_session)):
    """Get session by ID"""
    stmt = select(Session).where(Session.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    return session


@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(session_id: int, db: AsyncSession = Depends(get_session)):
    """End a streaming session"""
    stmt = select(Session).where(Session.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    session.status = "ended"
    session.ended_at = datetime.utcnow()

    await db.commit()
    await db.refresh(session)

    return session


@router.websocket("/ws/{session_token}")
async def websocket_endpoint(websocket: WebSocket, session_token: str):
    """WebSocket endpoint for WebRTC signaling"""
    await websocket.accept()

    try:
        # Verify session token
        async for db in get_session():
            stmt = select(Session).where(Session.session_token == session_token)
            result = await db.execute(stmt)
            session = result.scalar_one_or_none()

            if not session or session.status != "active":
                await websocket.close(code=1008, reason="Invalid or inactive session")
                return

            # Get device info
            stmt = select(Device).where(Device.id == session.device_id)
            result = await db.execute(stmt)
            device = result.scalar_one_or_none()

            if not device or device.status != "running":
                await websocket.close(code=1008, reason="Device not available")
                return

            break

        # Handle WebRTC signaling
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Process WebRTC messages (offer, answer, ice candidates)
            response = await webrtc_manager.handle_message(
                message, device.container_id, device.ip_address, device.webrtc_port
            )

            if response:
                await websocket.send_text(json.dumps(response))

    except WebSocketDisconnect:
        # Update session status
        async for db in get_session():
            stmt = select(Session).where(Session.session_token == session_token)
            result = await db.execute(stmt)
            session = result.scalar_one_or_none()

            if session:
                session.status = "disconnected"
                await db.commit()
            break

    except Exception as e:
        await websocket.close(code=1011, reason=str(e))
