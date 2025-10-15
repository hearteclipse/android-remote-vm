# WebRTC Setup Guide

The platform is built with **optional WebRTC support** to avoid complex build dependencies during initial setup.

## Current Status

✅ **Platform is functional** without WebRTC  
⚠️ **Video streaming** requires WebRTC packages  
✅ **Device management and API** work fully

## Installing WebRTC Support

### Option 1: Install in Running Container

```bash
# Enter the backend container
docker-compose exec backend bash

# Install WebRTC dependencies
pip install aiortc==1.6.0 av==11.0.0

# Restart the backend service
exit
docker-compose restart backend
```

### Option 2: Build With WebRTC from Start

Edit `backend/requirements.txt` and uncomment these lines:

```txt
# aiortc==1.6.0
# av==11.0.0
```

Then rebuild:

```bash
make clean
make build
make up
```

### Option 3: Use Pre-built Image (Future)

When available, you can use a pre-built image with WebRTC included:

```bash
docker pull gcr.io/your-project/vmi-backend:with-webrtc
```

## Troubleshooting WebRTC Installation

If `aiortc` or `av` fail to install, ensure these system packages are installed:

```bash
# On Debian/Ubuntu
apt-get update
apt-get install -y \
    gcc g++ make cmake \
    libavformat-dev libavcodec-dev libavdevice-dev \
    libavutil-dev libswscale-dev libswresample-dev \
    libavfilter-dev libopus-dev libvpx-dev libsrtp2-dev \
    pkg-config git
```

## Alternative: Use scrcpy for Streaming

If WebRTC is problematic, you can use scrcpy directly:

```bash
# On your local machine
scrcpy --serial=DEVICE_IP:5555
```

This connects directly to the Android device via ADB.

## Features Without WebRTC

Without WebRTC installed, you can still:

- ✅ Create and manage users
- ✅ Create virtual Android devices
- ✅ Start/stop/restart devices
- ✅ Monitor device metrics
- ✅ Use the admin dashboard
- ✅ Control devices via ADB commands
- ⚠️ No web-based video streaming (requires WebRTC)

## WebRTC Features (When Installed)

With WebRTC installed:

- ✅ Real-time video streaming in browser
- ✅ Low-latency touch/gesture forwarding
- ✅ WebSocket-based signaling
- ✅ Full web client functionality

---

**Recommendation**: Start without WebRTC to verify the platform works, then add WebRTC later if needed.

