# 🚀 Virtual Mobile Infrastructure (VMI) Platform

A complete dockerized platform for renting virtual Android devices with real-time WebRTC streaming, similar to Redfinger. Deploy on GCP or run locally.

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [API Documentation](#-api-documentation)
- [GCP Deployment](#-gcp-deployment)
- [Usage](#-usage)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)

## ✨ Features

- **Virtual Android Devices**: Run Android 11 emulators in Docker containers
- **Low-Latency H.264 Streaming**: Hardware-accelerated H.264 video via scrcpy/screenrecord
- **WebRTC Real-Time Communication**: Direct peer-to-peer streaming with STUN/TURN support
- **User Management**: Multi-tenant system with user isolation
- **Touch & Gesture Control**: Full touch, swipe, keyboard support via WebRTC DataChannel
- **Automatic Boot Detection**: Waits for Android to fully boot before streaming
- **Resource Management**: CPU, RAM limits and monitoring per device
- **Auto-scaling**: Automatic device lifecycle management
- **Admin Dashboard**: Real-time monitoring of users, devices, and metrics
- **REST API**: Complete FastAPI-based REST API with OpenAPI docs
- **GCP Ready**: Fully deployable on Google Cloud Platform

## 🏗️ Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────────┐
│   Client    │ ◄─────► │    Nginx     │ ◄─────► │  Backend API    │
│  (Browser)  │         │ (Reverse     │         │   (FastAPI)     │
│             │         │   Proxy)     │         │                 │
└──────┬──────┘         └──────────────┘         └────────┬────────┘
       │                                                   │
       │ WebRTC (H.264 Video + DataChannel Control)       │
       │                                         ┌─────────┴─────────┐
       │                                         │                   │
       │                                   ┌─────▼─────┐      ┌─────▼─────┐
       │                                   │ PostgreSQL│      │   Redis   │
       │                                   └───────────┘      └───────────┘
       │                                         │
       │                                         │ ADB Connection
       └─────────────────────────────────────────┼────────────────────┐
                                                 │                    │
                                         ┌───────▼────────┐    ┌──────▼───────┐
                                         │   Android      │    │   Android    │
                                         │  Container 1   │    │ Container N  │
                                         │  (Emulator +   │    │ (Emulator +  │
                                         │   scrcpy)      │    │  scrcpy)     │
                                         └────────────────┘    └──────────────┘
                                                ↓                      ↓
                                         H.264 Stream            H.264 Stream
                                         via scrcpy              via scrcpy
```

### Streaming Pipeline

1. **Android Device** → scrcpy server captures screen with hardware H.264 encoding
2. **scrcpy** → Streams H.264 via ADB to backend
3. **Backend (ffmpeg)** → Remuxes H.264 to MPEGTS (no re-encoding)
4. **Backend (aiortc)** → Wraps in WebRTC and sends to browser
5. **Browser** → Decodes H.264 with hardware acceleration and displays

**Result**: End-to-end latency of ~100-200ms with no server-side re-encoding!

## 📦 Prerequisites

### Local Development

- **Docker** >= 20.10
- **Docker Compose** >= 2.0
- **Python** >= 3.11 (for local development)
- **8GB RAM** minimum (16GB+ recommended)
- **KVM support** (optional, for hardware acceleration)

### GCP Deployment

- **Google Cloud SDK** installed and configured
- **GCP Project** with billing enabled
- **Compute Engine API** enabled
- **Cloud Run API** enabled
- **Container Registry API** enabled

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/android-remote-vm.git
cd android-remote-vm
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Build and Start Services

```bash
# Build all Docker images
make build

# Start all services
make up
```

Wait for services to initialize (this may take a few minutes on first run).

### 4. Access the Platform

- **Web Client**: http://localhost:8080
- **Admin Dashboard**: http://localhost:8080/admin
- **API Documentation**: http://localhost:8000/docs
- **API Alternative Docs**: http://localhost:8000/redoc

### 5. Create Your First User

```bash
curl -X POST "http://localhost:8000/api/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "securepassword123"
  }'
```

### 6. Create a Virtual Device

```bash
curl -X POST "http://localhost:8000/api/devices/?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "device_name": "My Android Device",
    "android_version": "11.0",
    "device_model": "Pixel_5",
    "cpu_allocated": 2,
    "ram_allocated": 2048
  }'
```

### 7. Start the Device

```bash
curl -X POST "http://localhost:8000/api/devices/1/control" \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```

### 8. Connect from Web Client

1. Open http://localhost:8080
2. Enter User ID: `1`
3. Select your device from the dropdown
4. Click "Connect to Device"

## 📁 Project Structure

```
android-remote-vm/
├── backend/                    # FastAPI backend application
│   ├── api/                   # API endpoints
│   │   ├── devices.py        # Device management endpoints
│   │   ├── users.py          # User management endpoints
│   │   └── sessions.py       # Session and streaming endpoints
│   ├── services/             # Business logic services
│   │   ├── database.py       # Database models and session
│   │   ├── vm_manager.py     # Docker container management
│   │   ├── webrtc_server.py  # WebRTC streaming server
│   │   ├── h264_streamer.py  # H.264 streaming via scrcpy/screenrecord
│   │   ├── adb_utils.py      # ADB connection and boot management
│   │   └── orchestrator.py   # VM lifecycle orchestration
│   ├── templates/            # HTML templates
│   │   └── dashboard.html    # Admin dashboard
│   ├── Dockerfile            # Backend Docker image
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Application configuration
│   └── requirements.txt     # Python dependencies
│
├── android/                   # Android emulator container
│   ├── emulator_config/      # Emulator configuration files
│   │   └── config.ini       # AVD configuration
│   ├── Dockerfile           # Android container image
│   ├── init.sh             # Container initialization script
│   └── webrtc_relay.py     # WebRTC relay server
│
├── client/                   # Web client application
│   └── web/
│       ├── index.html       # Client UI
│       └── stream.js        # WebRTC client logic
│
├── nginx/                    # Nginx reverse proxy
│   ├── nginx.conf           # Main nginx config
│   └── conf.d/
│       └── default.conf     # Site configuration
│
├── docker-compose.yml        # Docker Compose orchestration
├── Makefile                 # Build automation
├── .env.example            # Environment variables template
└── README.md              # This file
```

## ⚙️ Configuration

### Environment Variables

Key environment variables in `.env`:

```bash
# Database
DATABASE_URL=postgresql://vmi_user:vmi_password@postgres:5432/vmi_db

# Redis
REDIS_URL=redis://redis:6379

# Security (CHANGE IN PRODUCTION!)
SECRET_KEY=your-secret-key-change-in-production

# Resource Limits
MAX_DEVICES_PER_USER=5
MAX_CONCURRENT_SESSIONS=100

# WebRTC
WEBRTC_PORT_RANGE_START=49152
WEBRTC_PORT_RANGE_END=49252
WEBRTC_PUBLIC_IP=  # Set to your public IP for remote access
STUN_SERVER=stun:stun.l.google.com:19302
TURN_SERVER=turn:openrelay.metered.ca:80
TURN_USERNAME=openrelayproject
TURN_PASSWORD=openrelayproject
```

### Docker Compose Services

- **postgres**: PostgreSQL database for persistent data
- **redis**: Redis for caching and session management
- **backend**: FastAPI application server
- **nginx**: Reverse proxy and static file server

Android containers are created dynamically by the VM manager.

## 📚 API Documentation

### Interactive API Docs

Once the backend is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

#### Users

- `POST /api/users/` - Create a new user
- `GET /api/users/` - List all users
- `GET /api/users/{user_id}` - Get user details
- `PATCH /api/users/{user_id}` - Update user
- `DELETE /api/users/{user_id}` - Delete user

#### Devices

- `POST /api/devices/?user_id={id}` - Create a new device
- `GET /api/devices/` - List all devices
- `GET /api/devices/{device_id}` - Get device details
- `POST /api/devices/{device_id}/control` - Control device (start/stop/restart)
- `GET /api/devices/{device_id}/metrics` - Get device metrics
- `DELETE /api/devices/{device_id}` - Delete device

#### Sessions

- `POST /api/sessions/` - Create a streaming session
- `GET /api/sessions/` - List sessions
- `GET /api/sessions/{session_id}` - Get session details
- `POST /api/sessions/{session_id}/end` - End a session
- `WS /api/sessions/ws/{token}` - WebSocket for WebRTC signaling

## ☁️ GCP Deployment

### Step 1: Setup GCP Project

```bash
# Set your project ID
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="us-central1"

# Authenticate
gcloud auth login
gcloud config set project $GCP_PROJECT_ID
```

### Step 2: Enable Required APIs

```bash
gcloud services enable compute.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### Step 3: Create VM Instance with KVM Support

```bash
gcloud compute instances create vmi-host-1 \
  --machine-type=n2-standard-8 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=100GB \
  --boot-disk-type=pd-ssd \
  --enable-nested-virtualization \
  --zone=$GCP_REGION-a \
  --tags=vmi-host
```

### Step 4: SSH into VM and Install Docker

```bash
gcloud compute ssh vmi-host-1 --zone=$GCP_REGION-a

# On the VM
sudo apt update
sudo apt install -y docker.io docker-compose git make
sudo usermod -aG docker $USER
```

### Step 5: Deploy Application

```bash
# Clone repository
git clone https://github.com/yourusername/android-remote-vm.git
cd android-remote-vm

# Configure environment
cp .env.example .env
nano .env  # Edit configuration

# Build and start
make build
make up
```

### Step 6: Configure Firewall

```bash
# Allow HTTP/HTTPS traffic
gcloud compute firewall-rules create allow-vmi-http \
  --allow tcp:80,tcp:443,tcp:8000,tcp:8080 \
  --target-tags vmi-host

# Allow WebRTC ports (UDP is critical for WebRTC performance)
gcloud compute firewall-rules create allow-vmi-webrtc \
  --allow udp:49152-65535 \
  --source-ranges 0.0.0.0/0 \
  --target-tags vmi-host \
  --description="WebRTC UDP ports for VMI Platform"
```

### Step 7: Setup Cloud SQL (Optional, for Production)

For production, consider using Cloud SQL instead of containerized PostgreSQL:

```bash
gcloud sql instances create vmi-postgres \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$GCP_REGION

gcloud sql databases create vmi_db --instance=vmi-postgres

# Update DATABASE_URL in .env with Cloud SQL connection
```

### Step 8: Setup Load Balancer (Optional)

For high availability, setup a load balancer:

```bash
# Create instance group
gcloud compute instance-groups unmanaged create vmi-group \
  --zone=$GCP_REGION-a

gcloud compute instance-groups unmanaged add-instances vmi-group \
  --instances=vmi-host-1 \
  --zone=$GCP_REGION-a

# Create load balancer (follow GCP console for HTTP(S) LB setup)
```

## 💻 Usage

### Web Client

1. **Access**: Navigate to http://your-server:8080
2. **Select User**: Enter your user ID
3. **Choose Device**: Select a running device from the dropdown
4. **Connect**: Click "Connect to Device"
5. **Interact**: 
   - Click on the screen to tap
   - Use control buttons for system keys
   - Type text using your keyboard

### Admin Dashboard

Access http://your-server:8080/admin to:

- Monitor active users and sessions
- View running devices
- Check system metrics
- Manage resources

### API Usage Examples

#### Python

```python
import requests

BASE_URL = "http://localhost:8000/api"

# Create user
response = requests.post(f"{BASE_URL}/users/", json={
    "username": "john_doe",
    "email": "john@example.com",
    "password": "secure123"
})
user = response.json()

# Create device
response = requests.post(f"{BASE_URL}/devices/?user_id={user['id']}", json={
    "device_name": "My Phone",
    "android_version": "11.0",
    "device_model": "Pixel_5"
})
device = response.json()

# Start device
requests.post(f"{BASE_URL}/devices/{device['id']}/control", json={
    "action": "start"
})
```

#### cURL

```bash
# Create user
USER_ID=$(curl -s -X POST "http://localhost:8000/api/users/" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"pass123"}' \
  | jq -r '.id')

# Create device
DEVICE_ID=$(curl -s -X POST "http://localhost:8000/api/devices/?user_id=$USER_ID" \
  -H "Content-Type: application/json" \
  -d '{"device_name":"Test Device","android_version":"11.0"}' \
  | jq -r '.id')

# Start device
curl -X POST "http://localhost:8000/api/devices/$DEVICE_ID/control" \
  -H "Content-Type: application/json" \
  -d '{"action":"start"}'
```

## 🔧 Development

### Local Backend Development

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Start only database services
make dev-db

# Run backend with hot reload
make dev-backend
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
make test
```

### Adding New Features

1. **New API Endpoint**: Add to `backend/api/`
2. **New Service**: Add to `backend/services/`
3. **Database Changes**: Update models in `backend/services/database.py`
4. **Frontend Changes**: Update `client/web/`

### Building Custom Android Images

Customize the Android container by modifying:

- `android/Dockerfile` - Base image and installed packages
- `android/init.sh` - Initialization and configuration
- `android/emulator_config/config.ini` - AVD settings

## 🔍 Troubleshooting

### Container Won't Start

```bash
# Check logs
make logs

# Check specific service
docker-compose logs backend
docker-compose logs postgres
```

### Android Emulator Fails to Boot

```bash
# Check if KVM is available
ls -l /dev/kvm

# If not available, emulator will use software acceleration (slower)
# Check emulator logs
docker-compose logs
```

### WebRTC Connection Issues

1. **Check firewall**: Ensure UDP ports 49152-65535 are open
2. **Set public IP**: Set `WEBRTC_PUBLIC_IP` in `.env` to your server's public IP
3. **Check STUN/TURN**: Verify STUN_SERVER and TURN_SERVER in .env are accessible
4. **Browser console**: Check for WebRTC errors in browser console (F12)
5. **ICE connection**: Look for "ICE connection state: connected" in console
6. **Network**: Ensure client can reach server IP and UDP traffic is not blocked

### Android Device Not Showing Video

1. **Wait for boot**: Device takes 30-60s to fully boot after "start"
2. **Check scrcpy**: Run `docker exec <container> ps aux | grep scrcpy`
3. **Check ADB**: Run `docker exec vmi-backend adb devices` to see connected devices
4. **Fallback to screenrecord**: If scrcpy fails, system automatically tries screenrecord
5. **Container logs**: Check logs with `docker logs <android-container-id>`

### Black/Brown Screen

- **Cause**: Android device hasn't finished booting
- **Solution**: Wait 30-60 seconds after clicking "Connect"
- **Verify**: Backend logs should show "✅ Android device ready!"

### Database Connection Errors

```bash
# Reset database
docker-compose down -v
docker-compose up -d postgres redis
# Wait 10 seconds
docker-compose up backend
```

### Out of Resources

```bash
# Check system resources
docker stats

# Stop idle devices
curl -X POST "http://localhost:8000/api/devices/{device_id}/control" \
  -d '{"action":"stop"}'

# Adjust resource limits in docker-compose.yml
```

## 📊 Performance Optimization

### Hardware Acceleration

Enable KVM for better performance:

```bash
# Check KVM support
egrep -c '(vmx|svm)' /proc/cpuinfo  # Should be > 0

# Load KVM module
sudo modprobe kvm
sudo modprobe kvm_intel  # or kvm_amd for AMD
```

### Resource Allocation

Adjust per-device resources in API requests:

```json
{
  "device_name": "High Performance Device",
  "cpu_allocated": 4,
  "ram_allocated": 4096
}
```

### Scaling

For production workloads:

1. **Horizontal**: Deploy multiple VM hosts
2. **Vertical**: Use larger GCP instance types (n2-standard-16+)
3. **Database**: Use Cloud SQL with connection pooling
4. **Caching**: Scale Redis with Cloud Memorystore

## 🔒 Security Considerations

⚠️ **Important for Production**:

1. **Change default passwords** in `.env`
2. **Enable HTTPS** with proper SSL certificates
3. **Implement authentication** (JWT, OAuth2)
4. **Use Cloud SQL** instead of containerized PostgreSQL
5. **Enable firewall rules** properly
6. **Limit API rate** to prevent abuse
7. **Regular backups** of database
8. **Monitor logs** for suspicious activity

## 📄 License

This project is licensed under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

For issues and questions:

- Open an issue on GitHub
- Check existing documentation
- Review troubleshooting section

## 🙏 Acknowledgments

- Android Emulator in Docker: [budtmo/docker-android](https://github.com/budtmo/docker-android)
- WebRTC: [aiortc](https://github.com/aiortc/aiortc)
- FastAPI: [tiangolo/fastapi](https://github.com/tiangolo/fastapi)

---

**Built with ❤️ for the Android developer community**

