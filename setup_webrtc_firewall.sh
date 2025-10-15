#!/bin/bash
# Script to configure GCP firewall for WebRTC

echo "🔧 Configuring GCP firewall for WebRTC..."

# Create firewall rule for WebRTC UDP ports
gcloud compute firewall-rules create allow-webrtc-udp \
    --allow=udp:49152-49252 \
    --source-ranges=0.0.0.0/0 \
    --description="Allow WebRTC UDP traffic for android-remote-vm" \
    --network=default

echo "✅ Firewall rule created!"
echo ""
echo "Firewall rules:"
gcloud compute firewall-rules list --filter="name=allow-webrtc-udp"

