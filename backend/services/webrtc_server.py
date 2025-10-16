import asyncio
import logging
from typing import Dict, Optional
import json
import subprocess
import fractions

from config import settings
from services.h264_streamer import H264Player, ScreenrecordPlayer

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
                elif pc.connectionState == "closed":
                    # Cleanup H.264 player when connection closes
                    if hasattr(pc, "_h264_player"):
                        await pc._h264_player.stop()

            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logger.info(f"🧊 Backend ICE connection state: {pc.iceConnectionState}")

            @pc.on("icegatheringstatechange")
            async def on_icegatheringstatechange():
                logger.info(f"🧊 Backend ICE gathering state: {pc.iceGatheringState}")

            @pc.on("track")
            def on_track(track):
                logger.info(f"📹 Track received: {track.kind}")

            @pc.on("datachannel")
            def on_datachannel(channel):
                logger.info(f"📡 DataChannel opened: {channel.label}")

                @channel.on("message")
                async def on_message(message):
                    """Handle control messages from client"""
                    try:
                        data = json.loads(message)
                        await self._handle_datachannel_message(data, device_ip)
                    except Exception as e:
                        logger.error(f"Error handling datachannel message: {e}")

            # Create H.264 video stream from Android device
            # Try scrcpy first (lower latency), fallback to screenrecord
            device_serial = f"{device_ip}:5555"
            logger.info(f"Starting H.264 stream for {device_serial}...")

            try:
                h264_player = H264Player(device_serial)
                await h264_player.start()
                logger.info("✅ Using scrcpy H.264 stream (low latency)")
            except Exception as scrcpy_error:
                logger.warning(f"Scrcpy failed: {scrcpy_error}, trying screenrecord...")
                try:
                    h264_player = ScreenrecordPlayer(device_serial)
                    await h264_player.start()
                    logger.info("✅ Using screenrecord H.264 stream")
                except Exception as screenrecord_error:
                    logger.error(f"Screenrecord also failed: {screenrecord_error}")
                    raise RuntimeError("Both scrcpy and screenrecord failed")

            # Store player reference for cleanup
            pc._h264_player = h264_player

            # Add H.264 video track to peer connection
            video_track = h264_player.video()
            if video_track:
                pc.addTrack(video_track)
                logger.info("H.264 video track added to peer connection")
            else:
                raise RuntimeError("Failed to get video track from H.264 player")

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
        # sourcery skip: low-code-quality
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

    async def _handle_datachannel_message(self, data: Dict, device_ip: str):
        """Handle messages from WebRTC DataChannel (touch, swipe, etc.)"""
        try:
            msg_type = data.get("type")
            device_serial = f"{device_ip}:5555"

            # Display dimensions (should match H.264 stream size)
            DISPLAY_W, DISPLAY_H = 1280, 720

            if msg_type == "tap":
                # Normalized coordinates (0..1) from client
                x_norm = data.get("x", 0)
                y_norm = data.get("y", 0)

                # Convert to pixel coordinates
                px = max(0, min(int(x_norm * DISPLAY_W), DISPLAY_W - 1))
                py = max(0, min(int(y_norm * DISPLAY_H), DISPLAY_H - 1))

                logger.info(f"👆 Tap at ({px}, {py})")

                cmd = f"adb -s {device_serial} shell input tap {px} {py}"
                proc = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

            elif msg_type == "swipe":
                # Swipe gesture
                x1 = max(0, min(int(data.get("x1", 0) * DISPLAY_W), DISPLAY_W - 1))
                y1 = max(0, min(int(data.get("y1", 0) * DISPLAY_H), DISPLAY_H - 1))
                x2 = max(0, min(int(data.get("x2", 0) * DISPLAY_W), DISPLAY_W - 1))
                y2 = max(0, min(int(data.get("y2", 0) * DISPLAY_H), DISPLAY_H - 1))
                duration = data.get("duration", 300)

                logger.info(f"👉 Swipe from ({x1},{y1}) to ({x2},{y2})")

                cmd = f"adb -s {device_serial} shell input swipe {x1} {y1} {x2} {y2} {duration}"
                proc = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

            elif msg_type == "keyevent":
                keycode = data.get("keycode")
                logger.info(f"⌨️ Keyevent: {keycode}")

                cmd = f"adb -s {device_serial} shell input keyevent {keycode}"
                proc = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

        except Exception as e:
            logger.error(f"Error handling datachannel message: {e}")

    async def _handle_input(self, message: Dict, device_ip: str) -> Dict:
        """Handle user input (touch, keyboard, etc.) - legacy WebSocket method"""
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
            self.adb_connected = False
            self.last_good_frame = None
            logger.info(f"AndroidVideoTrack initialized for {device_ip}:{port}")

        async def _ensure_adb_connected(self):
            """Ensure ADB is connected to the device"""
            if self.adb_connected:
                return True

            try:
                # Try to connect to ADB device
                connect_cmd = ["adb", "connect", f"{self.device_ip}:5555"]
                connect_proc = await asyncio.create_subprocess_exec(
                    *connect_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await connect_proc.communicate()
                result = stdout.decode().strip()
                logger.info(f"🔌 ADB connect result: {result}")

                # Check if connected successfully
                if (
                    "connected" in result.lower()
                    or "already connected" in result.lower()
                ):
                    self.adb_connected = True
                    logger.info(f"✅ ADB connected to {self.device_ip}:5555")
                    return True
                else:
                    logger.error(f"❌ ADB connection failed: {result}")
                    return False

            except Exception as e:
                logger.error(f"❌ Failed to connect ADB: {e}")
                return False

        async def recv(self):  # sourcery skip: low-code-quality
            """Receive next video frame from Android screen"""
            if self.counter == 0:
                logger.info("🎥 FIRST recv() call - video streaming starting!")
                logger.info(f"📱 Capturing screen from {self.device_ip}")

            # Ensure ADB is connected
            if not await self._ensure_adb_connected():
                # If ADB connection fails, return test pattern
                await asyncio.sleep(1 / 30)
                self.counter += 1
                if self.last_good_frame:
                    return self.last_good_frame

                img = np.zeros((720, 1280, 3), dtype=np.uint8)
                img[:, :, 0] = 100
                img[:, :, 1] = 50
                img[:, :, 2] = 50

                frame = VideoFrame.from_ndarray(img, format="rgb24")
                frame.pts = self.counter
                frame.time_base = fractions.Fraction(1, 30)
                return frame

            try:
                import asyncio
                from concurrent.futures import ThreadPoolExecutor

                # Use ThreadPoolExecutor to avoid blocking the event loop
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as pool:
                    # Take a screenshot using ADB screencap (PNG format)
                    # This is simpler and more reliable than H264 streaming
                    cmd = [
                        "adb",
                        "-s",
                        f"{self.device_ip}:5555",
                        "exec-out",
                        "screencap",
                        "-p",
                    ]

                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    stdout, stderr = await process.communicate()

                    if stderr and self.counter < 5:  # Only log first few errors
                        logger.warning(f"ADB stderr: {stderr.decode()[:100]}")

                    if not stdout or len(stdout) < 100:
                        if self.counter < 5:
                            logger.error("❌ Failed to capture screenshot, retrying...")
                        # Retry connection on next frame
                        self.adb_connected = False
                        # sourcery skip: raise-specific-error
                        raise Exception("Screenshot capture failed")

                    # Decode PNG to numpy array
                    import io
                    from PIL import Image

                    img_pil = Image.open(io.BytesIO(stdout))
                    img = np.array(img_pil)

                    # Convert RGBA to RGB if needed
                    if img.shape[2] == 4:
                        img = img[:, :, :3]

                    # Resize to standard resolution if needed (for performance)
                    if img.shape[0] > 720:
                        img_pil = img_pil.resize((1280, 720), Image.LANCZOS)
                        img = np.array(img_pil)
                        if img.shape[2] == 4:
                            img = img[:, :, :3]

                    self.counter += 1

                    # Create VideoFrame
                    frame = VideoFrame.from_ndarray(img, format="rgb24")
                    frame.pts = self.counter
                    frame.time_base = fractions.Fraction(1, 30)

                    # Store last good frame
                    self.last_good_frame = frame

                    if (
                        self.counter == 1 or self.counter % 30 == 0
                    ):  # Log first and every second
                        logger.info(
                            f"📸 Captured frame {self.counter} ({img.shape[1]}x{img.shape[0]})"
                        )

                    # Control framerate (30 fps)
                    await asyncio.sleep(1 / 30)

                    return frame

            except Exception as e:
                if self.counter < 5:
                    logger.error(f"❌ Error capturing frame: {e}")

                # Fallback to last good frame or test pattern
                await asyncio.sleep(1 / 30)
                self.counter += 1

                if self.last_good_frame:
                    return self.last_good_frame

                img = np.zeros((720, 1280, 3), dtype=np.uint8)
                img[:, :, 0] = 100
                img[:, :, 1] = 50
                img[:, :, 2] = 50

                frame = VideoFrame.from_ndarray(img, format="rgb24")
                frame.pts = self.counter
                frame.time_base = fractions.Fraction(1, 30)

                return frame

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
