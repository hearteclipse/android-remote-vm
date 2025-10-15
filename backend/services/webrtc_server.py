import asyncio
import logging
from typing import Dict, Optional
import json
import subprocess

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

        # Configure STUN/TURN servers
        self.rtc_config = RTCConfiguration(
            iceServers=[RTCIceServer(urls=[settings.STUN_SERVER])]
        )

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

            # Create video track from Android screen
            video_track = AndroidVideoTrack(device_ip, webrtc_port)
            pc.addTrack(video_track)

            # Set remote description
            offer = RTCSessionDescription(sdp=message["sdp"], type=message["type"])
            await pc.setRemoteDescription(offer)

            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            logger.info(f"WebRTC connection established for {container_id}")

            return {"type": "answer", "sdp": pc.localDescription.sdp}

        except Exception as e:
            logger.error(f"Error handling offer: {e}")
            raise

    async def _handle_ice_candidate(self, message: Dict, container_id: str) -> None:
        """Handle ICE candidate"""
        try:
            if pc := self.peer_connections.get(container_id):
                # In production, you would add ICE candidates properly
                # This is a simplified version
                logger.info(f"Received ICE candidate for {container_id}")

        except Exception as e:
            logger.error(f"Error handling ICE candidate: {e}")

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
            try:
                # In production, you would decode the H264 stream
                # and convert to VideoFrame
                # This is a placeholder implementation

                # Create a test pattern frame (blue gradient for testing)
                import time

                img = np.zeros((720, 1280, 3), dtype=np.uint8)
                # Add a color gradient to verify video is working
                img[:, :, 0] = 100  # Blue channel
                img[:, :, 1] = int((time.time() % 1.0) * 255)  # Green channel animates
                img[:, :, 2] = 50  # Red channel

                frame = VideoFrame.from_ndarray(img, format="bgr24")
                frame.pts = self.next_timestamp()
                frame.time_base = "1/90000"

                return frame

            except Exception as e:
                logger.error(f"Error receiving frame: {e}")
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
