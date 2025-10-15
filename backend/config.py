from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Database
    DATABASE_URL: str = "postgresql://vmi_user:vmi_password@postgres:5432/vmi_db"

    # Redis
    REDIS_URL: str = "redis://redis:6379"

    # Docker
    DOCKER_HOST: str = "unix:///var/run/docker.sock"
    ANDROID_NETWORK: str = "vmi-network"

    # Android Emulator Settings
    ANDROID_BASE_IMAGE: str = "budtmo/docker-android:emulator_11.0"
    EMULATOR_DEVICE: str = "Pixel_5"
    EMULATOR_ARCH: str = "x86_64"

    # WebRTC Settings
    WEBRTC_PORT_RANGE_START: int = 49152
    WEBRTC_PORT_RANGE_END: int = 49252
    WEBRTC_PUBLIC_IP: Optional[str] = None  # Set via env var for GCP deployment
    STUN_SERVER: str = "stun:stun.l.google.com:19302"

    # TURN server for NAT traversal (free public server)
    TURN_SERVER: str = "turn:openrelay.metered.ca:80"
    TURN_USERNAME: str = "openrelayproject"
    TURN_PASSWORD: str = "openrelayproject"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Limits
    MAX_DEVICES_PER_USER: int = 5
    MAX_CONCURRENT_SESSIONS: int = 100

    # GCP Settings (for deployment)
    GCP_PROJECT_ID: Optional[str] = None
    GCP_REGION: Optional[str] = "us-central1"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
