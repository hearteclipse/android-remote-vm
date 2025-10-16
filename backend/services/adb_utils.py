"""ADB utility functions for managing Android device connections and boot status"""

import asyncio
import shlex
import logging

logger = logging.getLogger(__name__)


async def run(cmd: str):
    """Execute a shell command and return (returncode, output)"""
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    out, _ = await proc.communicate()
    return proc.returncode, (out or b"").decode("utf-8", "ignore")


async def adb_wait_for_boot(serial: str, timeout=120):
    """Wait for Android device to complete boot process"""
    logger.info(f"⏳ Waiting for {serial} to complete boot (timeout: {timeout}s)...")

    # Wait for device to appear
    rc, _ = await run(f"adb -s {shlex.quote(serial)} wait-for-device")
    if rc != 0:
        raise RuntimeError(f"ADB wait-for-device failed for {serial}")

    # Wait for boot completion properties
    for i in range(timeout):
        rc, out = await run(
            f"adb -s {shlex.quote(serial)} shell getprop sys.boot_completed"
        )
        if out.strip() == "1":
            rc2, out2 = await run(
                f"adb -s {shlex.quote(serial)} shell getprop dev.bootcomplete"
            )
            if out2.strip() == "1":
                logger.info(f"✅ {serial} boot completed!")

                # Unlock screen if locked
                await run(f"adb -s {shlex.quote(serial)} shell input keyevent 82")

                # Disable animations for better stability
                await run(
                    f"adb -s {shlex.quote(serial)} shell settings put global window_animation_scale 0"
                )
                await run(
                    f"adb -s {shlex.quote(serial)} shell settings put global transition_animation_scale 0"
                )
                await run(
                    f"adb -s {shlex.quote(serial)} shell settings put global animator_duration_scale 0"
                )

                logger.info(f"🎬 Animations disabled on {serial}")
                return

        if i % 10 == 0 and i > 0:
            logger.info(f"⏳ Still waiting for boot... ({i}s elapsed)")

        await asyncio.sleep(1)

    raise TimeoutError(f"Android device {serial} did not complete boot in {timeout}s")


async def adb_ensure_connected(serial: str):
    """Ensure ADB is connected to the device, reconnect if needed"""
    try:
        rc, out = await run("adb devices")
        if serial in out:
            return True

        # Try to connect
        logger.info(f"🔌 Connecting to {serial}...")
        rc, out = await run(f"adb connect {serial}")

        if "connected" in out.lower() or "already connected" in out.lower():
            logger.info(f"✅ Connected to {serial}")
            return True
        else:
            logger.warning(f"⚠️ Failed to connect to {serial}: {out}")
            return False

    except Exception as e:
        logger.error(f"❌ Error ensuring ADB connection to {serial}: {e}")
        return False


async def adb_start_server():
    """Start ADB server with recommended settings"""
    try:
        # Kill existing server
        await run("adb kill-server")
        await asyncio.sleep(1)

        # Start server
        logger.info("🚀 Starting ADB server...")
        rc, out = await run("adb start-server")

        if rc == 0:
            logger.info("✅ ADB server started successfully")
            return True
        else:
            logger.error(f"❌ Failed to start ADB server: {out}")
            return False

    except Exception as e:
        logger.error(f"❌ Error starting ADB server: {e}")
        return False
