import asyncio
import logging
from typing import Dict, Optional
import json
import subprocess
import fractions

from config import settings

logger = logging.getLogger(__name__)

# WebRTC imports - optional, will be needed for full functionality
try:
    from aiortc import (
        RTCPeerConnection,
        RTCSessionDescription,
        VideoStreamTrack,
        RTCConfiguration,
        RTCIceServer,
    )
    from aiortc.contrib.media import MediaRelay
    from av import VideoFrame
    import numpy as np

    WEBRTC_AVAILABLE = True
except ImportError:
    logger.warning("aiortc not installed. WebRTC streaming will not be available.")
    logger.info("To enable WebRTC: pip install aiortc av numpy")
    WEBRTC_AVAILABLE = False
    RTCPeerConnection = None
    RTCSessionDescription = None
    VideoStreamTrack = None
    RTCConfiguration = None
    RTCIceServer = None
    MediaRelay = None
    VideoFrame = None


class WebRTCManager:
    """Manages WebRTC connections for Android device streaming"""

    def __init__(self):
        self.peer_connections = {}

        if not WEBRTC_AVAILABLE:
            logger.warning("WebRTC Manager initialized WITHOUT WebRTC support")
            self.media_relay = None
            self.rtc_config = None
            return

        self.media_relay = MediaRelay()

        # Configure STUN/TURN servers for NAT traversal
        ice_servers = [RTCIceServer(urls=[settings.STUN_SERVER])]

        # Add TURN server for NAT traversal
        ice_servers.append(
            RTCIceServer(
                urls=[settings.TURN_SERVER],
                username=settings.TURN_USERNAME,
                credential=settings.TURN_PASSWORD,
            )
        )

        self.rtc_config = RTCConfiguration(iceServers=ice_servers)

        # Log public IP configuration
        if settings.WEBRTC_PUBLIC_IP:
            logger.info(
                f"WebRTC configured with public IP: {settings.WEBRTC_PUBLIC_IP}"
            )
        else:
            logger.warning("WEBRTC_PUBLIC_IP not set - NAT traversal may fail")

        logger.info("WebRTC Manager initialized with full WebRTC support")

    async def handle_message(
        self, message: Dict, container_id: str, device_ip: str, webrtc_port: int
    ) -> Optional[Dict]:
        """Handle WebRTC signaling messages"""
        if not WEBRTC_AVAILABLE:
            return {
                "type": "error",
                "message": "WebRTC not available. Install aiortc: pip install aiortc av numpy",
            }

        try:
            msg_type = message.get("type")

            if msg_type == "offer":
                return await self._handle_offer(
                    message, container_id, device_ip, webrtc_port
                )

            elif msg_type == "ice-candidate":
                return await self._handle_ice_candidate(message, container_id)

            elif msg_type == "input":
                return await self._handle_input(message, device_ip)

            else:
                logger.warning(f"Unknown message type: {msg_type}")
                return None

        except Exception as e:
            logger.error(f"Error handling WebRTC message: {e}")
            return {"type": "error", "message": str(e)}

    async def _handle_offer(
        self, message: Dict, container_id: str, device_ip: str, webrtc_port: int
    ) -> Dict:
        """Handle WebRTC offer and create answer"""
        try:
            # Create peer connection
            pc = RTCPeerConnection(configuration=self.rtc_config)
            self.peer_connections[container_id] = pc

            # Add event handlers for debugging
            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(f"🔌 Backend connection state: {pc.connectionState}")
                if pc.connectionState == "connected":
                    logger.info("✅ Backend WebRTC connection fully established!")
                elif pc.connectionState == "failed":
                    logger.error("❌ Backend WebRTC connection failed!")

            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logger.info(f"🧊 Backend ICE connection state: {pc.iceConnectionState}")

            @pc.on("icegatheringstatechange")
            async def on_icegatheringstatechange():
                logger.info(f"🧊 Backend ICE gathering state: {pc.iceGatheringState}")

            @pc.on("track")
            def on_track(track):
                logger.info(f"📹 Track received: {track.kind}")

            # Create video track from Android screen BEFORE setting remote description
            logger.info(f"Creating AndroidVideoTrack for {device_ip}:{webrtc_port}")
            video_track = AndroidVideoTrack(device_ip, webrtc_port)
            pc.addTrack(video_track)
            logger.info("Video track added to peer connection")

            # Now set remote description
            offer = RTCSessionDescription(sdp=message["sdp"], type=message["type"])
            await pc.setRemoteDescription(offer)

            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            # Modify SDP to use public IP if configured
            answer_sdp = pc.localDescription.sdp
            if settings.WEBRTC_PUBLIC_IP:
                # Replace private IPs with public IP in SDP
                import re

                # Replace c= lines with public IP
                answer_sdp = re.sub(
                    r"c=IN IP4 (\d+\.\d+\.\d+\.\d+)",
                    f"c=IN IP4 {settings.WEBRTC_PUBLIC_IP}",
                    answer_sdp,
                )
                logger.info(
                    f"Modified SDP to use public IP: {settings.WEBRTC_PUBLIC_IP}"
                )

            logger.info(f"WebRTC connection established for {container_id}")
            logger.info(f"Answer SDP (first 200 chars): {answer_sdp[:200]}...")

            return {"type": "answer", "sdp": answer_sdp}

        except Exception as e:
            logger.error(f"Error handling offer: {e}")
            raise

    async def _handle_ice_candidate(self, message: Dict, container_id: str) -> None:
        """Handle ICE candidate from client"""
        try:
            if pc := self.peer_connections.get(container_id):
                from aiortc import RTCIceCandidate

                candidate_data = message.get("candidate", {})

                # Extract ICE candidate string
                candidate_str = candidate_data.get("candidate", "")
                sdp_mid = candidate_data.get("sdpMid")
                sdp_mline_index = candidate_data.get("sdpMLineIndex", 0)

                if candidate_str:
                    logger.info(
                        f"🧊 Received remote ICE candidate for {container_id[:12]}"
                    )
                    logger.debug(f"   Candidate: {candidate_str[:80]}...")
                    logger.debug(
                        f"   sdpMid: {sdp_mid}, sdpMLineIndex: {sdp_mline_index}"
                    )

                    try:
                        from aiortc import RTCIceCandidate

                        # Parse ICE candidate manually from the string
                        # Format: "candidate:foundation component protocol priority ip port typ type ..."
                        parts = candidate_str.split()

                        if len(parts) < 8:
                            raise ValueError(
                                f"Invalid candidate format: {candidate_str}"
                            )

                        # Extract fields from candidate string
                        foundation = (
                            parts[0].split(":")[1] if ":" in parts[0] else parts[0]
                        )
                        component = int(parts[1])
                        protocol = parts[2]
                        priority = int(parts[3])
                        ip = parts[4]
                        port = int(parts[5])
                        typ_idx = parts.index("typ")
                        cand_type = parts[typ_idx + 1]

                        # Create RTCIceCandidate
                        ice_candidate = RTCIceCandidate(
                            component=component,
                            foundation=foundation,
                            ip=ip,
                            port=port,
                            priority=priority,
                            protocol=protocol,
                            type=cand_type,
                            sdpMid=sdp_mid,
                            sdpMLineIndex=sdp_mline_index,
                        )

                        # Add related address if present (for srflx/relay)
                        if "raddr" in parts and "rport" in parts:
                            raddr_idx = parts.index("raddr")
                            rport_idx = parts.index("rport")
                            ice_candidate.relatedAddress = parts[raddr_idx + 1]
                            ice_candidate.relatedPort = (
                                int(parts[rport_idx + 1])
                                if parts[rport_idx + 1] != "0"
                                else None
                            )

                        # Add to peer connection
                        await pc.addIceCandidate(ice_candidate)
                        logger.info(
                            f"✅ Remote ICE candidate added: {cand_type} {ip}:{port}"
                        )
                    except Exception as parse_error:
                        logger.error(f"❌ Failed to parse ICE candidate: {parse_error}")
                        logger.error(f"   Full candidate: {candidate_str}")
                        logger.error(f"   Raw data: {candidate_data}")
                else:
                    logger.info(
                        f"🧊 ICE gathering complete signal received for {container_id[:12]}"
                    )

        except Exception as e:
            logger.error(f"❌ Error handling ICE candidate: {e}", exc_info=True)

    async def _handle_input(self, message: Dict, device_ip: str) -> Dict:
        """Handle user input (touch, keyboard, etc.)"""
        try:
            input_type = message.get("inputType")

            if input_type == "touch":
                await self._send_touch_event(
                    device_ip,
                    message.get("x"),
                    message.get("y"),
                    message.get("action", "tap"),
                )

            elif input_type == "key":
                await self._send_key_event(device_ip, message.get("keyCode"))

            elif input_type == "text":
                await self._send_text(device_ip, message.get("text"))

            return {"type": "input-ack", "success": True}

        except Exception as e:
            logger.error(f"Error handling input: {e}")
            return {"type": "input-ack", "success": False, "error": str(e)}

    async def _send_touch_event(self, device_ip: str, x: int, y: int, action: str):
        """Send touch event to Android device via ADB"""
        try:
            if action == "tap":
                cmd = f"adb -s {device_ip}:5555 shell input tap {x} {y}"
            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

        except Exception as e:
            logger.error(f"Error sending touch event: {e}")

    async def _send_key_event(self, device_ip: str, keycode: int):
        """Send key event to Android device via ADB"""
        try:
            cmd = f"adb -s {device_ip}:5555 shell input keyevent {keycode}"

            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

        except Exception as e:
            logger.error(f"Error sending key event: {e}")

    async def _send_text(self, device_ip: str, text: str):
        """Send text input to Android device via ADB"""
        try:
            # Escape text for shell
            escaped_text = text.replace(" ", "%s")
            cmd = f"adb -s {device_ip}:5555 shell input text '{escaped_text}'"

            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

        except Exception as e:
            logger.error(f"Error sending text: {e}")

    async def close_connection(self, container_id: str):
        """Close WebRTC connection"""
        try:
            if pc := self.peer_connections.get(container_id):
                await pc.close()
                del self.peer_connections[container_id]
                logger.info(f"Closed WebRTC connection for {container_id}")

        except Exception as e:
            logger.error(f"Error closing connection: {e}")


if WEBRTC_AVAILABLE:

    class AndroidVideoTrack(VideoStreamTrack):
        """Video track that captures Android screen"""

        def __init__(self, device_ip: str, port: int):
            super().__init__()
            self.device_ip = device_ip
            self.port = port
            self.process = None
            self.counter = 0
            logger.info(f"AndroidVideoTrack initialized for {device_ip}:{port}")
            self._start_capture()

        def _start_capture(self):
            """Start screen capture from Android device using scrcpy or ADB"""
            try:
                # Use scrcpy for efficient screen capture
                # Fallback to ADB screencap if scrcpy not available
                cmd = [
                    "adb",
                    "-s",
                    f"{self.device_ip}:5555",
                    "exec-out",
                    "screenrecord",
                    "--output-format=h264",
                    "-",
                ]

                self.process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )

                logger.info(f"Started screen capture for {self.device_ip}")

            except Exception as e:
                logger.error(f"Error starting screen capture: {e}")

        async def recv(self):
            """Receive next video frame"""
            if self.counter == 0:
                logger.info("🎥 FIRST recv() call - video streaming starting!")
            try:
                # In production, you would decode the H264 stream
                # and convert to VideoFrame
                # This is a placeholder implementation

                # Create a test pattern frame (blue gradient for testing)
                import time
                import asyncio

                # Control framerate (30 fps)
                await asyncio.sleep(1 / 30)

                img = np.zeros((720, 1280, 3), dtype=np.uint8)
                # Add a color gradient to verify video is working
                img[:, :, 0] = 100  # Blue channel
                img[:, :, 1] = int((time.time() % 1.0) * 255)  # Green channel animates
                img[:, :, 2] = 50  # Red channel

                # Add a moving white bar to verify animation
                bar_pos = int((self.counter % 100) * 7.2)
                img[bar_pos : bar_pos + 10, :] = 255
                self.counter += 1

                frame = VideoFrame.from_ndarray(img, format="bgr24")
                frame.pts = self.counter
                frame.time_base = fractions.Fraction(1, 30)

                if self.counter % 30 == 0:  # Log every second
                    logger.info(f"Sending frame {self.counter}")

                return frame

            except Exception as e:
                logger.error(f"Error receiving frame: {e}", exc_info=True)
                raise

        def __del__(self):
            """Cleanup"""
            if self.process:
                self.process.terminate()

else:

    class AndroidVideoTrack:
        """Dummy video track when WebRTC is not available"""

        def __init__(self, device_ip: str, port: int):
            self.device_ip = device_ip
            self.port = port
            logger.warning("AndroidVideoTrack created but WebRTC is not available")
