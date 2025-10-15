#!/bin/bash

echo "Starting Android Virtual Device..."

# Set default values if not provided
DEVICE=${DEVICE:-"Pixel_5"}
EMULATOR_ARGS=${EMULATOR_ARGS:-"-no-window -no-audio -gpu swiftshader_indirect"}
ADB_PORT=${ADB_PORT:-5555}
WEBRTC_PORT=${WEBRTC_PORT:-50000}

echo "Device: $DEVICE"
echo "Emulator Args: $EMULATOR_ARGS"
echo "ADB Port: $ADB_PORT"
echo "WebRTC Port: $WEBRTC_PORT"

# Start ADB server
echo "Starting ADB server..."
adb start-server
adb devices

# Check if KVM is available
if [ -e /dev/kvm ]; then
    echo "KVM is available, using hardware acceleration"
    EMULATOR_ARGS="$EMULATOR_ARGS -accel on -qemu -enable-kvm"
else
    echo "KVM not available, using software acceleration"
fi

# Create AVD if not exists
AVD_NAME="android_vmi"
if [ ! -d "/root/.android/avd/${AVD_NAME}.avd" ]; then
    echo "Creating AVD: $AVD_NAME"
    echo "no" | avdmanager create avd \
        -n "$AVD_NAME" \
        -k "system-images;android-30;google_apis;x86_64" \
        -d "$DEVICE" \
        --force
fi

# Start emulator in background
echo "Starting Android emulator..."
emulator -avd "$AVD_NAME" \
    $EMULATOR_ARGS \
    -port 5554 \
    -no-boot-anim \
    -no-snapshot \
    -wipe-data \
    &

EMULATOR_PID=$!
echo "Emulator started with PID: $EMULATOR_PID"

# Wait for emulator to boot
echo "Waiting for emulator to boot..."
adb wait-for-device
echo "Emulator device detected"

# Wait for boot to complete
BOOT_COMPLETED=0
RETRY_COUNT=0
MAX_RETRIES=60

while [ $BOOT_COMPLETED -eq 0 ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    BOOT_STATUS=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
    
    if [ "$BOOT_STATUS" = "1" ]; then
        BOOT_COMPLETED=1
        echo "Emulator boot completed!"
    else
        echo "Waiting for boot... ($RETRY_COUNT/$MAX_RETRIES)"
        sleep 5
        RETRY_COUNT=$((RETRY_COUNT + 1))
    fi
done

if [ $BOOT_COMPLETED -eq 0 ]; then
    echo "ERROR: Emulator failed to boot within timeout"
    exit 1
fi

# Configure emulator
echo "Configuring emulator..."

# Disable screen lock
adb shell settings put secure lock_screen_disabled 1

# Set screen always on
adb shell settings put system screen_off_timeout 2147483647

# Enable USB debugging
adb shell settings put global adb_enabled 1

# Set screen density
adb shell wm density 420

# Enable network on emulator
adb shell svc wifi enable
adb shell svc data enable

echo "Emulator configuration complete"

# Start WebRTC relay server
echo "Starting WebRTC relay server on port $WEBRTC_PORT..."
python3 /root/webrtc_relay.py --port $WEBRTC_PORT &

WEBRTC_PID=$!
echo "WebRTC relay started with PID: $WEBRTC_PID"

# Keep container running and monitor processes
echo "Container is ready!"
echo "================================"
echo "ADB: adb connect localhost:$ADB_PORT"
echo "WebRTC: localhost:$WEBRTC_PORT"
echo "================================"

# Monitor emulator process
while kill -0 $EMULATOR_PID 2>/dev/null; do
    sleep 10
done

echo "Emulator process ended, shutting down container"
kill $WEBRTC_PID 2>/dev/null
exit 0

