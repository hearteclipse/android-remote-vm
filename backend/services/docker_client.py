"""
Ultra-simple Docker client that actually works
"""

import docker
import logging

logger = logging.getLogger(__name__)


class SimpleDockerClient:
    """Simple Docker client that bypasses all the complex initialization"""

    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Docker client using raw socket approach"""
        import os
        import socket
        import json

        # Clear ALL Docker environment variables first
        docker_vars = [
            "DOCKER_HOST",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
            "DOCKER_MACHINE_NAME",
            "DOCKER_CONFIG",
            "DOCKER_CONTEXT",
        ]
        old_vars = {}
        for var in docker_vars:
            if var in os.environ:
                old_vars[var] = os.environ[var]
                del os.environ[var]

        try:
            # Method 1: Test raw socket connection first
            logger.info("Testing raw socket connection...")
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect("/var/run/docker.sock")
            request = "GET /version HTTP/1.1\r\nHost: localhost\r\n\r\n"
            sock.send(request.encode())
            response = sock.recv(4096).decode()
            sock.close()

            if "HTTP/1.1 200 OK" in response:
                logger.info("✅ Raw socket connection successful!")

                # Now try the Python docker library with explicit socket
                logger.info("Attempting DockerClient with explicit socket...")
                self.client = docker.DockerClient(
                    base_url="unix:///var/run/docker.sock"
                )
                self.client.ping()
                logger.info("✅ DockerClient with explicit socket successful!")
                return
            else:
                logger.warning(f"Raw socket test failed: {response[:100]}")

        except Exception as e:
            logger.warning(f"Raw socket test failed: {e}")

        try:
            # Method 2: Force from_env with explicit socket override
            logger.info("Attempting from_env with socket override...")
            os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"
            self.client = docker.from_env()
            self.client.ping()
            logger.info("✅ from_env with socket override successful!")
            return
        except Exception as e:
            logger.warning(f"from_env with socket override failed: {e}")

        try:
            # Method 3: Try API client only (no high-level client)
            logger.info("Attempting API client only...")
            api = docker.APIClient(base_url="unix:///var/run/docker.sock")
            api.ping()
            # Create a wrapper that uses the API client directly
            self.client = self._create_api_wrapper(api)
            logger.info("✅ API client wrapper successful!")
            return
        except Exception as e:
            logger.warning(f"API client failed: {e}")

        logger.error("❌ All Docker connection methods failed!")
        self.client = None

        # Restore environment variables
        for var, value in old_vars.items():
            os.environ[var] = value

    def _create_api_wrapper(self, api_client):
        """Create a wrapper around API client to mimic DockerClient interface"""

        class APIClientWrapper:
            def __init__(self, api):
                self.api = api

            def ping(self):
                return self.api.ping()

            @property
            def containers(self):
                return self.api

            @property
            def images(self):
                return self.api

            def version(self):
                return self.api.version()

        return APIClientWrapper(api_client)

    def is_available(self) -> bool:
        """Check if Docker client is available"""
        return self.client is not None

    def get_client(self):
        """Get the Docker client"""
        return self.client

    def create_container(self, **kwargs):
        """Create a container"""
        if not self.client:
            raise Exception("Docker client not available")
        return self.client.containers.run(**kwargs)

    def get_container(self, container_id):
        """Get a container by ID"""
        if not self.client:
            raise Exception("Docker client not available")
        return self.client.containers.get(container_id)

    def list_containers(self, **kwargs):
        """List containers"""
        if not self.client:
            raise Exception("Docker client not available")
        return self.client.containers.list(**kwargs)

    def remove_container(self, container_id, **kwargs):
        """Remove a container"""
        if not self.client:
            raise Exception("Docker client not available")
        container = self.client.containers.get(container_id)
        return container.remove(**kwargs)
