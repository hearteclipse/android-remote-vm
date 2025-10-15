import os
import docker
from docker.errors import DockerException, NotFound
import logging
from typing import Dict, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import psutil

from config import settings

logger = logging.getLogger(__name__)


class DockerRuntime:
    _client = None

    @classmethod
    def client(cls):
        if cls._client is None:
            base_url = os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
            try:
                cls._client = docker.DockerClient(base_url=base_url)
                # valida conexão (vai falhar se faltar requests-unixsocket ou socket)
                cls._client.ping()
            except Exception as e:
                raise RuntimeError(
                    f"Docker client not available (base_url={base_url}). "
                    "Check requests-unixsocket, docker.sock mount and permissions."
                ) from e
        return cls._client

    @classmethod
    def start_android_vm(cls, device):
        client = cls.client()
        name = f"android-{device.id}"
        image = settings.ANDROID_BASE_IMAGE  # ex: "ghcr.io/.../android-webrtc:latest"

        # Container configuration
        environment = {
            "DEVICE": device.device_model,
            "EMULATOR_ARGS": "-no-window -no-audio -gpu swiftshader_indirect",
            "ADB_PORT": str(getattr(device, "adb_port", 5555)),
            "WEBRTC_PORT": str(getattr(device, "webrtc_port", 8080)),
        }

        ports = {}
        if hasattr(device, "adb_port") and device.adb_port:
            ports[f"{device.adb_port}/tcp"] = device.adb_port
        if hasattr(device, "webrtc_port") and device.webrtc_port:
            ports[f"{device.webrtc_port}/tcp"] = device.webrtc_port

        # TODO: ajuste volumes/ports/envs conforme seu container Android
        container = client.containers.run(
            image=image,
            name=name,
            detach=True,
            privileged=True,  # se precisa de /dev/kvm no Linux
            environment=environment,
            ports=ports,
            volumes=getattr(device, "volumes", {}),
            restart_policy={"Name": "unless-stopped"},
            network=settings.ANDROID_NETWORK,
            mem_limit=f"{device.ram_allocated}m",
            cpu_count=device.cpu_allocated,
        )
        return container


class VMManager:
    """Manages Android virtual device containers"""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.port_allocator = PortAllocator()

        try:
            # Test DockerRuntime client
            logger.info("Initializing Docker client...")
            client = DockerRuntime.client()
            logger.info("✅ VMManager initialized with DockerRuntime")
        except Exception as e:
            logger.error(f"❌ VMManager initialization failed: {e}")
            raise

    async def start_device(self, device) -> Dict:
        """Start an Android emulator container"""
        try:
            logger.info(f"Starting device {device.id}: {device.device_name}")

            # Allocate ports
            webrtc_port = self.port_allocator.allocate_port()
            adb_port = self.port_allocator.allocate_port()

            # Set ports on device object
            device.webrtc_port = webrtc_port
            device.adb_port = adb_port

            # Use DockerRuntime to start container
            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(
                self.executor, DockerRuntime.start_android_vm, device
            )

            # Get container IP
            container.reload()
            networks = container.attrs["NetworkSettings"]["Networks"]
            ip_address = networks.get(settings.ANDROID_NETWORK, {}).get("IPAddress", "")

            if not ip_address:
                # Fallback to default network
                ip_address = container.attrs["NetworkSettings"].get(
                    "IPAddress", "localhost"
                )

            logger.info(f"Device {device.id} started: {container.id[:12]}")

            return {
                "container_id": container.id,
                "ip_address": ip_address,
                "webrtc_port": webrtc_port,
                "adb_port": adb_port,
                "status": "running",
            }

        except Exception as e:
            logger.error(f"Failed to start device {device.id}: {e}")
            raise

    def _create_container(self, name, environment, webrtc_port, adb_port, device):
        """Create and start Docker container (runs in thread pool)"""
        try:
            # Remove existing container if any
            try:
                client = DockerRuntime.client()
                old_container = client.containers.get(name)
                old_container.remove(force=True)
                logger.info(f"Removed old container: {name}")
            except NotFound:
                pass

            # Create container
            client = DockerRuntime.client()
            container = client.containers.run(
                image=settings.ANDROID_BASE_IMAGE,
                name=name,
                environment=environment,
                ports={
                    f"{adb_port}/tcp": adb_port,
                    f"{webrtc_port}/tcp": webrtc_port,
                },
                devices=["/dev/kvm"] if self._check_kvm_available() else [],
                privileged=True,
                detach=True,
                network=settings.ANDROID_NETWORK,
                mem_limit=f"{device.ram_allocated}m",
                cpu_count=device.cpu_allocated,
                restart_policy={"Name": "unless-stopped"},
            )

            return container

        except Exception as e:
            logger.error(f"Error creating container: {e}")
            raise

    async def stop_device(self, device):
        """Stop an Android emulator container"""
        try:
            if not device.container_id:
                logger.warning(f"Device {device.id} has no container ID")
                return

            logger.info(f"Stopping device {device.id}")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor, self._stop_container, device.container_id
            )

            # Free allocated ports
            if device.webrtc_port:
                self.port_allocator.free_port(device.webrtc_port)
            if device.adb_port:
                self.port_allocator.free_port(device.adb_port)

            logger.info(f"Device {device.id} stopped")

        except Exception as e:
            logger.error(f"Failed to stop device {device.id}: {e}")
            raise

    def _stop_container(self, container_id):
        """Stop Docker container (runs in thread pool)"""
        try:
            client = DockerRuntime.client()
            container = client.containers.get(container_id)
            container.stop(timeout=10)
        except NotFound:
            logger.warning(f"Container {container_id} not found")
        except Exception as e:
            logger.error(f"Error stopping container: {e}")
            raise

    async def restart_device(self, device):
        """Restart an Android emulator container"""
        try:
            logger.info(f"Restarting device {device.id}")

            if device.container_id:
                await self.stop_device(device)

            return await self.start_device(device)

        except Exception as e:
            logger.error(f"Failed to restart device {device.id}: {e}")
            raise

    async def remove_device(self, device):
        """Remove an Android emulator container"""
        try:
            if not device.container_id:
                return

            logger.info(f"Removing device {device.id}")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor, self._remove_container, device.container_id
            )

            # Free allocated ports
            if device.webrtc_port:
                self.port_allocator.free_port(device.webrtc_port)
            if device.adb_port:
                self.port_allocator.free_port(device.adb_port)

            logger.info(f"Device {device.id} removed")

        except Exception as e:
            logger.error(f"Failed to remove device {device.id}: {e}")
            raise

    def _remove_container(self, container_id):
        """Remove Docker container (runs in thread pool)"""
        try:
            client = DockerRuntime.client()
            container = client.containers.get(container_id)
            container.remove(force=True)
        except NotFound:
            logger.warning(f"Container {container_id} not found")
        except Exception as e:
            logger.error(f"Error removing container: {e}")
            raise

    async def get_container_metrics(self, container_id: str) -> Dict:
        """Get container resource usage metrics"""
        try:
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(
                self.executor, self._get_container_stats, container_id
            )

            return stats

        except Exception as e:
            logger.error(f"Failed to get metrics for {container_id}: {e}")
            return {"cpu_usage": 0, "ram_usage": 0, "network_in": 0, "network_out": 0}

    def _get_container_stats(self, container_id):
        """Get container stats (runs in thread pool)"""
        try:
            client = DockerRuntime.client()
            container = client.containers.get(container_id)
            stats = container.stats(stream=False)

            # Calculate CPU usage
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"]
                - stats["precpu_stats"]["system_cpu_usage"]
            )
            cpu_count = stats["cpu_stats"].get("online_cpus", 1)

            cpu_usage = 0.0
            if system_delta > 0:
                cpu_usage = (cpu_delta / system_delta) * cpu_count * 100.0

            # Calculate memory usage
            ram_usage = stats["memory_stats"].get("usage", 0) / (
                1024 * 1024
            )  # Convert to MB

            # Network stats
            networks = stats.get("networks", {})
            network_in = sum(net.get("rx_bytes", 0) for net in networks.values()) / (
                1024 * 1024
            )
            network_out = sum(net.get("tx_bytes", 0) for net in networks.values()) / (
                1024 * 1024
            )

            return {
                "cpu_usage": round(cpu_usage, 2),
                "ram_usage": round(ram_usage, 2),
                "network_in": round(network_in, 2),
                "network_out": round(network_out, 2),
            }

        except Exception as e:
            logger.error(f"Error getting container stats: {e}")
            return {"cpu_usage": 0, "ram_usage": 0, "network_in": 0, "network_out": 0}

    def _check_kvm_available(self) -> bool:
        """Check if KVM is available on the host"""
        try:
            import os

            return os.path.exists("/dev/kvm")
        except:
            return False


class PortAllocator:
    """Manages port allocation for containers"""

    def __init__(self):
        self.allocated_ports = set()
        self.current_port = settings.WEBRTC_PORT_RANGE_START

    def allocate_port(self) -> int:
        """Allocate an available port"""
        while self.current_port <= settings.WEBRTC_PORT_RANGE_END:
            if self.current_port not in self.allocated_ports:
                port = self.current_port
                self.allocated_ports.add(port)
                self.current_port += 1
                return port
            self.current_port += 1

        raise Exception("No available ports in range")

    def free_port(self, port: int):
        """Free an allocated port"""
        if port in self.allocated_ports:
            self.allocated_ports.remove(port)
