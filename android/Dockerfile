# Android Emulator Docker Container
FROM budtmo/docker-android:emulator_11.0

# Set environment variables
ENV DEVICE="Samsung Galaxy S10"
ENV ANDROID_VERSION=11.0
ENV API_LEVEL=30

# Install additional tools
USER root
RUN apt-get update && apt-get install -y \
    ffmpeg \
    v4l2loopback-dkms \
    v4l2loopback-utils \
    socat \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for WebRTC
RUN pip3 install --no-cache-dir \
    aiortc \
    aiohttp \
    websockets

# Copy initialization script
COPY init.sh /root/init.sh
RUN chmod +x /root/init.sh

# Copy WebRTC server script
COPY webrtc_relay.py /root/webrtc_relay.py

# Expose ports
# 5555: ADB
# 6080: noVNC (web interface)
# 50000-51000: WebRTC ports
EXPOSE 5555 6080 50000-51000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD adb devices | grep emulator || exit 1

# Set entrypoint
ENTRYPOINT ["/root/init.sh"]

