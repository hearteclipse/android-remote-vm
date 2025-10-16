#!/bin/bash
# Deploy H.264 streaming improvements to production

set -e

echo "🚀 Deploying H.264 Low-Latency Streaming Update"
echo "=============================================="

# Check if WEBRTC_PUBLIC_IP is set
if [ -z "$WEBRTC_PUBLIC_IP" ]; then
    echo "⚠️  WEBRTC_PUBLIC_IP not set in environment"
    echo "Please set it before deploying:"
    echo "  export WEBRTC_PUBLIC_IP=34.42.79.210"
    exit 1
fi

echo "✅ WEBRTC_PUBLIC_IP: $WEBRTC_PUBLIC_IP"

# Stop services
echo ""
echo "🛑 Stopping existing services..."
docker-compose down

# Build new images
echo ""
echo "🔨 Building updated images..."
docker-compose build backend android

# Start services
echo ""
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to start..."
sleep 10

# Check service health
echo ""
echo "🔍 Checking service health..."
docker-compose ps

echo ""
echo "📋 Backend logs (last 20 lines):"
docker-compose logs --tail=20 backend

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Open http://$WEBRTC_PUBLIC_IP:8080/ in your browser"
echo "2. Create a device and start it"
echo "3. Wait 30-60s for Android to boot"
echo "4. Connect and enjoy H.264 streaming!"
echo ""
echo "Monitor logs with: docker-compose logs -f backend"

