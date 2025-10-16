"""H.264 streaming using scrcpy and ffmpeg for low-latency Android screen capture"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Check for aiortc availability
try:
    from aiortc.contrib.media import MediaPlayer

    AIORTC_AVAILABLE = True
except ImportError:
    logger.warning("aiortc not available - H.264 streaming will not work")
    MediaPlayer = None
    AIORTC_AVAILABLE = False


class H264Player:
    """H.264 player using scrcpy + ffmpeg pipeline for low-latency streaming"""

    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self.scrcpy_proc = None
        self.ffmpeg_proc = None
        self.player = None
        self.pipe_path = None
        logger.info(f"H264Player initialized for device {device_serial}")

    async def start(self):
        """Start scrcpy server and ffmpeg remuxer pipeline"""
        if not AIORTC_AVAILABLE:
            raise RuntimeError("aiortc not available - cannot start H.264 player")

        try:
            # Start scrcpy server on Android device
            # It will stream H.264 to a local TCP port
            logger.info(f"🎥 Starting scrcpy server for {self.device_serial}...")

            # Push scrcpy server to device if needed
            push_cmd = [
                "adb",
                "-s",
                self.device_serial,
                "push",
                "/usr/local/bin/scrcpy-server.jar",
                "/data/local/tmp/scrcpy-server.jar",
            ]
            push_proc = await asyncio.create_subprocess_exec(
                *push_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await push_proc.communicate()

            # Start scrcpy server on device (streams to port 27183)
            scrcpy_cmd = [
                "adb",
                "-s",
                self.device_serial,
                "shell",
                "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
                "app_process",
                "/",
                "com.genymobile.scrcpy.Server",
                "2.3.1",
                "tunnel_forward=true",
                "control=false",
                "video_bit_rate=8000000",
                "max_fps=60",
                "lock_video_orientation=0",
                "max_size=1280",
            ]

            self.scrcpy_proc = await asyncio.create_subprocess_exec(
                *scrcpy_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait a bit for scrcpy to initialize
            await asyncio.sleep(2)

            # Forward the port from device to host
            forward_cmd = [
                "adb",
                "-s",
                self.device_serial,
                "forward",
                "tcp:27183",
                "localabstract:scrcpy",
            ]
            forward_proc = await asyncio.create_subprocess_exec(
                *forward_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await forward_proc.communicate()

            logger.info("✅ Scrcpy server started, port forwarded")

            # Start ffmpeg to remux H.264 from TCP to MPEGTS on stdout
            # This allows aiortc MediaPlayer to consume the stream
            logger.info("🎬 Starting ffmpeg remuxer...")

            ffmpeg_cmd = [
                "ffmpeg",
                "-i",
                "tcp://127.0.0.1:27183",
                "-c",
                "copy",  # No re-encoding, just copy H.264
                "-f",
                "mpegts",
                "pipe:1",
            ]

            self.ffmpeg_proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            logger.info("✅ FFmpeg remuxer started")

            # Create MediaPlayer to read from stdin (ffmpeg pipes to it)
            # We need to create a custom player that reads from the process
            import os
            import tempfile

            # Create a named pipe for ffmpeg output
            self.pipe_path = f"/tmp/scrcpy_{self.device_serial.replace(':', '_')}.ts"
            try:
                os.remove(self.pipe_path)
            except:
                pass
            os.mkfifo(self.pipe_path)

            # Restart ffmpeg to write to the named pipe
            self.ffmpeg_proc.kill()
            await self.ffmpeg_proc.wait()

            ffmpeg_cmd = [
                "ffmpeg",
                "-i",
                "tcp://127.0.0.1:27183",
                "-c",
                "copy",  # No re-encoding, just copy H.264
                "-f",
                "mpegts",
                self.pipe_path,
            ]

            self.ffmpeg_proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            # Wait a moment for pipe to be ready
            await asyncio.sleep(0.5)

            # Create MediaPlayer from the named pipe
            self.player = MediaPlayer(self.pipe_path, format="mpegts")

            logger.info("✅ H.264 pipeline ready!")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to start H.264 player: {e}")
            await self.stop()
            raise

    def video(self):
        """Get video track from the player"""
        if self.player:
            return self.player.video
        return None

    async def stop(self):
        """Stop all processes in the pipeline"""
        try:
            # Stop ffmpeg
            if self.ffmpeg_proc:
                try:
                    self.ffmpeg_proc.kill()
                    await self.ffmpeg_proc.wait()
                except:
                    pass

            # Stop scrcpy
            if self.scrcpy_proc:
                try:
                    self.scrcpy_proc.kill()
                    await self.scrcpy_proc.wait()
                except:
                    pass

            # Remove port forward
            try:
                remove_forward = await asyncio.create_subprocess_exec(
                    "adb",
                    "-s",
                    self.device_serial,
                    "forward",
                    "--remove",
                    "tcp:27183",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await remove_forward.communicate()
            except:
                pass

            # Remove named pipe
            if self.pipe_path:
                try:
                    import os

                    os.remove(self.pipe_path)
                except:
                    pass

            logger.info("🛑 H.264 player stopped")

        except Exception as e:
            logger.error(f"Error stopping H.264 player: {e}")


class ScreenrecordPlayer:
    """Fallback H.264 player using screenrecord (higher latency)"""

    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self.adb_proc = None
        self.ffmpeg_proc = None
        self.player = None
        self.pipe_path = None
        logger.info(f"ScreenrecordPlayer initialized for device {device_serial}")

    async def start(self):
        """Start screenrecord + ffmpeg pipeline"""
        if not AIORTC_AVAILABLE:
            raise RuntimeError(
                "aiortc not available - cannot start screenrecord player"
            )

        try:
            logger.info(f"🎥 Starting screenrecord for {self.device_serial}...")

            # Start ADB screenrecord
            adb_cmd = [
                "adb",
                "-s",
                self.device_serial,
                "exec-out",
                "screenrecord",
                "--output-format=h264",
                "--size",
                "1280x720",
                "--bit-rate",
                "8000000",
                "-",
            ]

            self.adb_proc = await asyncio.create_subprocess_exec(
                *adb_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Create a named pipe for ffmpeg output
            import os

            self.pipe_path = (
                f"/tmp/screenrecord_{self.device_serial.replace(':', '_')}.ts"
            )
            try:
                os.remove(self.pipe_path)
            except:
                pass
            os.mkfifo(self.pipe_path)

            # Start ffmpeg to remux from ADB stdout to named pipe
            ffmpeg_cmd = [
                "ffmpeg",
                "-f",
                "h264",
                "-i",
                "pipe:0",
                "-c",
                "copy",
                "-f",
                "mpegts",
                self.pipe_path,
            ]

            self.ffmpeg_proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=self.adb_proc.stdout,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            # Wait for pipe to be ready
            await asyncio.sleep(0.5)

            # Create MediaPlayer from named pipe
            self.player = MediaPlayer(self.pipe_path, format="mpegts")

            logger.info("✅ Screenrecord pipeline ready!")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to start screenrecord player: {e}")
            await self.stop()
            raise

    def video(self):
        """Get video track from the player"""
        if self.player:
            return self.player.video
        return None

    async def stop(self):
        """Stop all processes"""
        try:
            if self.ffmpeg_proc:
                self.ffmpeg_proc.kill()
                await self.ffmpeg_proc.wait()

            if self.adb_proc:
                self.adb_proc.kill()
                await self.adb_proc.wait()

            # Remove named pipe
            if self.pipe_path:
                try:
                    import os

                    os.remove(self.pipe_path)
                except:
                    pass

            logger.info("🛑 Screenrecord player stopped")

        except Exception as e:
            logger.error(f"Error stopping screenrecord player: {e}")
