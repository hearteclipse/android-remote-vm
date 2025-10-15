import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import select

from services.database import async_session, Device, Session
from services.vm_manager import VMManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates VM lifecycle and resource management"""

    def __init__(self):
        self.vm_manager = VMManager()
        self.running = False
        self.tasks = []
        logger.info("Orchestrator initialized")

    async def start(self):
        """Start orchestrator background tasks"""
        self.running = True

        # Start background tasks
        self.tasks.append(asyncio.create_task(self._cleanup_idle_devices()))
        self.tasks.append(asyncio.create_task(self._monitor_resources()))
        self.tasks.append(asyncio.create_task(self._cleanup_stale_sessions()))

        logger.info("Orchestrator started")

    async def stop(self):
        """Stop orchestrator background tasks"""
        self.running = False

        # Cancel all tasks
        for task in self.tasks:
            task.cancel()

        await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("Orchestrator stopped")

    async def _cleanup_idle_devices(self):
        """Stop devices that have been idle for too long"""
        while self.running:
            try:
                async with async_session() as db:
                    # Find devices idle for more than 30 minutes
                    idle_threshold = datetime.utcnow() - timedelta(minutes=30)

                    stmt = select(Device).where(
                        Device.status == "running", Device.last_used < idle_threshold
                    )
                    result = await db.execute(stmt)
                    idle_devices = result.scalars().all()

                    for device in idle_devices:
                        logger.info(f"Stopping idle device: {device.id}")
                        await self.vm_manager.stop_device(device)
                        device.status = "stopped"
                        await db.commit()

            except Exception as e:
                logger.error(f"Error in cleanup_idle_devices: {e}")

            # Run every 5 minutes
            await asyncio.sleep(300)

    async def _monitor_resources(self):
        """Monitor system resources and take action if needed"""
        while self.running:
            try:
                # Check system CPU and memory
                import psutil

                cpu_percent = psutil.cpu_percent(interval=1)
                memory_percent = psutil.virtual_memory().percent

                logger.info(
                    f"System resources - CPU: {cpu_percent}%, RAM: {memory_percent}%"
                )

                # If resources are critically high, stop some devices
                if cpu_percent > 90 or memory_percent > 90:
                    await self._emergency_resource_cleanup()

            except Exception as e:
                logger.error(f"Error in monitor_resources: {e}")

            # Run every minute
            await asyncio.sleep(60)

    async def _emergency_resource_cleanup(self):
        """Emergency cleanup when resources are critically high"""
        try:
            logger.warning("Emergency resource cleanup triggered")

            async with async_session() as db:
                # Stop least recently used devices
                stmt = (
                    select(Device)
                    .where(Device.status == "running")
                    .order_by(Device.last_used.asc())
                    .limit(5)
                )

                result = await db.execute(stmt)
                devices_to_stop = result.scalars().all()

                for device in devices_to_stop:
                    logger.warning(f"Emergency stopping device: {device.id}")
                    await self.vm_manager.stop_device(device)
                    device.status = "stopped"
                    await db.commit()

        except Exception as e:
            logger.error(f"Error in emergency_resource_cleanup: {e}")

    async def _cleanup_stale_sessions(self):
        """Clean up sessions that have been disconnected for too long"""
        while self.running:
            try:
                async with async_session() as db:
                    # Find sessions disconnected for more than 1 hour
                    stale_threshold = datetime.utcnow() - timedelta(hours=1)

                    stmt = select(Session).where(
                        Session.status == "disconnected",
                        Session.started_at < stale_threshold,
                    )
                    result = await db.execute(stmt)
                    stale_sessions = result.scalars().all()

                    for session in stale_sessions:
                        logger.info(f"Ending stale session: {session.id}")
                        session.status = "ended"
                        session.ended_at = datetime.utcnow()
                        await db.commit()

            except Exception as e:
                logger.error(f"Error in cleanup_stale_sessions: {e}")

            # Run every 10 minutes
            await asyncio.sleep(600)

    async def scale_up(self, count: int = 1):
        """Pre-provision devices for faster allocation"""
        # This could be used to pre-create warm pools of devices
        pass

    async def scale_down(self, count: int = 1):
        """Remove idle pre-provisioned devices"""
        # This could be used to reduce warm pool size
        pass


# Global orchestrator instance
orchestrator = Orchestrator()
