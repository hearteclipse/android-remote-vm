"""
RAW Docker Client - Bypasses all Python docker library issues
"""
import socket
import json
import logging
import subprocess
import os

logger = logging.getLogger(__name__)

class RawDockerClient:
    """Raw Docker client that uses direct socket communication"""
    
    def __init__(self):
        self.socket_path = "/var/run/docker.sock"
        self._test_connection()
    
    def _test_connection(self):
        """Test if we can connect to Docker socket"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.socket_path)
            sock.close()
            logger.info("✅ Raw Docker socket connection successful!")
        except Exception as e:
            logger.error(f"❌ Raw Docker socket connection failed: {e}")
            raise
    
    def _send_request(self, method, path, data=None):
        """Send raw HTTP request to Docker socket"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.socket_path)
            
            # Build HTTP request
            if data:
                body = json.dumps(data).encode()
                headers = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
                request = headers.encode() + body
            else:
                headers = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n\r\n"
                request = headers.encode()
            
            sock.send(request)
            
            # Read response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"\r\n\r\n" in response and (b"Content-Length:" not in response or len(response) > 10000):
                    break
            
            sock.close()
            
            # Parse response
            response_str = response.decode()
            if "HTTP/1.1 200" in response_str or "HTTP/1.1 201" in response_str:
                # Extract JSON body
                body_start = response_str.find("\r\n\r\n")
                if body_start != -1:
                    body = response_str[body_start + 4:]
                    if body.strip():
                        return json.loads(body)
                return {"status": "success"}
            else:
                logger.error(f"Docker API error: {response_str[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Raw request failed: {e}")
            return None
    
    def ping(self):
        """Ping Docker daemon"""
        result = self._send_request("GET", "/_ping")
        return result is not None
    
    def version(self):
        """Get Docker version"""
        return self._send_request("GET", "/version")
    
    def create_container(self, image, **kwargs):
        """Create a container using raw API"""
        config = {
            "Image": image,
            "Cmd": kwargs.get("command", ["sleep", "infinity"]),
            "Env": kwargs.get("environment", []),
            "ExposedPorts": {},
            "HostConfig": {
                "PortBindings": {},
                "NetworkMode": kwargs.get("network", "bridge")
            }
        }
        
        # Handle ports
        if "ports" in kwargs:
            for container_port, host_port in kwargs["ports"].items():
                port_num = container_port.split("/")[0]
                config["ExposedPorts"][container_port] = {}
                config["HostConfig"]["PortBindings"][container_port] = [{"HostPort": str(host_port)}]
        
        # Handle environment variables
        if "environment" in kwargs:
            config["Env"] = [f"{k}={v}" for k, v in kwargs["environment"].items()]
        
        # Create container
        result = self._send_request("POST", "/containers/create", config)
        if result and "Id" in result:
            container_id = result["Id"]
            
            # Start container
            start_result = self._send_request("POST", f"/containers/{container_id}/start")
            if start_result is not None:
                return {"id": container_id, "status": "running"}
        
        return None
    
    def get_container(self, container_id):
        """Get container info"""
        return self._send_request("GET", f"/containers/{container_id}/json")
    
    def list_containers(self, all=False):
        """List containers"""
        path = "/containers/json"
        if all:
            path += "?all=true"
        return self._send_request("GET", path)
    
    def remove_container(self, container_id, force=False):
        """Remove container"""
        path = f"/containers/{container_id}"
        if force:
            path += "?force=true"
        return self._send_request("DELETE", path)
    
    def stop_container(self, container_id):
        """Stop container"""
        return self._send_request("POST", f"/containers/{container_id}/stop")
    
    def start_container(self, container_id):
        """Start container"""
        return self._send_request("POST", f"/containers/{container_id}/start")

# Wrapper to mimic DockerClient interface
class RawDockerWrapper:
    """Wrapper to mimic DockerClient interface"""
    
    def __init__(self):
        self.raw_client = RawDockerClient()
    
    def ping(self):
        return self.raw_client.ping()
    
    def version(self):
        return self.raw_client.version()
    
    @property
    def containers(self):
        return self.raw_client
