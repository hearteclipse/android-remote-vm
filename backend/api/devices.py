from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from services.database import get_session, Device, User
from services.vm_manager import VMManager

router = APIRouter()
vm_manager = VMManager()


# Pydantic schemas
class DeviceCreate(BaseModel):
    device_name: str
    android_version: str = "11.0"
    device_model: str = "Pixel_5"
    cpu_allocated: int = 2
    ram_allocated: int = 2048


class DeviceResponse(BaseModel):
    id: int
    user_id: int
    container_id: Optional[str]
    device_name: str
    android_version: str
    device_model: str
    status: str
    ip_address: Optional[str]
    webrtc_port: Optional[int]
    adb_port: Optional[int]
    created_at: datetime
    last_used: datetime
    cpu_allocated: int
    ram_allocated: int

    class Config:
        from_attributes = True


class DeviceControl(BaseModel):
    action: str  # start, stop, restart


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    user_id: int,
    device_data: DeviceCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """Create a new virtual Android device"""
    # Check user exists
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check device limit
    stmt = select(Device).where(Device.user_id == user_id)
    result = await db.execute(stmt)
    user_devices = result.scalars().all()

    if len(user_devices) >= user.max_devices:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum device limit ({user.max_devices}) reached",
        )

    # Create device record
    new_device = Device(
        user_id=user_id,
        device_name=device_data.device_name,
        android_version=device_data.android_version,
        device_model=device_data.device_model,
        cpu_allocated=device_data.cpu_allocated,
        ram_allocated=device_data.ram_allocated,
        status="stopped",
    )

    db.add(new_device)
    await db.commit()
    await db.refresh(new_device)

    return new_device


@router.get("/", response_model=List[DeviceResponse])
async def list_devices(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_session),
):
    """List all devices, optionally filtered by user"""
    if user_id:
        stmt = select(Device).where(Device.user_id == user_id).offset(skip).limit(limit)
    else:
        stmt = select(Device).offset(skip).limit(limit)

    result = await db.execute(stmt)
    devices = result.scalars().all()
    return devices


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int, db: AsyncSession = Depends(get_session)):
    """Get device by ID"""
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )

    return device


@router.post("/{device_id}/control", response_model=DeviceResponse)
async def control_device(
    device_id: int,
    control: DeviceControl,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """Start, stop, or restart a device"""
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )

    if control.action == "start":
        # Start the container
        container_info = await vm_manager.start_device(device)
        device.status = "running"
        device.container_id = container_info.get("container_id")
        device.ip_address = container_info.get("ip_address")
        device.webrtc_port = container_info.get("webrtc_port")
        device.adb_port = container_info.get("adb_port")
        device.last_used = datetime.utcnow()

    elif control.action == "stop":
        await vm_manager.stop_device(device)
        device.status = "stopped"

    elif control.action == "restart":
        await vm_manager.restart_device(device)
        device.status = "running"
        device.last_used = datetime.utcnow()

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Use 'start', 'stop', or 'restart'",
        )

    await db.commit()
    await db.refresh(device)

    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: int, db: AsyncSession = Depends(get_session)):
    """Delete a device"""
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )

    # Stop and remove container if running
    if device.container_id:
        await vm_manager.remove_device(device)

    await db.delete(device)
    await db.commit()

    return None


@router.get("/{device_id}/metrics")
async def get_device_metrics(device_id: int, db: AsyncSession = Depends(get_session)):
    """Get real-time device metrics"""
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
        )

    if device.status != "running" or not device.container_id:
        return {"cpu_usage": 0, "ram_usage": 0, "network_in": 0, "network_out": 0}

    metrics = await vm_manager.get_container_metrics(device.container_id)
    return metrics
