from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Float,
)
from datetime import datetime
from config import settings

# Convert PostgreSQL URL to async version
DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# Create session factory
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Base class for models
Base = declarative_base()


# Database Models
class User(Base):
    """User model"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    max_devices = Column(Integer, default=5)


class Device(Base):
    """Android virtual device model"""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    container_id = Column(String(100), unique=True, index=True)
    device_name = Column(String(100), nullable=False)
    android_version = Column(String(20), default="11.0")
    device_model = Column(String(50), default="Pixel_5")
    status = Column(String(20), default="stopped")  # stopped, starting, running, error
    ip_address = Column(String(50))
    webrtc_port = Column(Integer)
    adb_port = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, default=datetime.utcnow)
    cpu_allocated = Column(Integer, default=2)  # CPU cores
    ram_allocated = Column(Integer, default=2048)  # MB


class Session(Base):
    """User session with virtual device"""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    session_token = Column(String(255), unique=True, index=True)
    status = Column(String(20), default="active")  # active, disconnected, ended
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    data_transferred = Column(Float, default=0.0)  # MB


class Metric(Base):
    """Device performance metrics"""

    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    cpu_usage = Column(Float, default=0.0)  # percentage
    ram_usage = Column(Float, default=0.0)  # MB
    network_in = Column(Float, default=0.0)  # MB
    network_out = Column(Float, default=0.0)  # MB
    timestamp = Column(DateTime, default=datetime.utcnow)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections"""
    await engine.dispose()


async def get_session() -> AsyncSession:
    """Get database session"""
    async with async_session() as session:
        yield session
