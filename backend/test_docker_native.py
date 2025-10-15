#!/usr/bin/env python3
"""
Docker Connection Test - Native Socket Approach
"""
import os
import sys
import socket
import json


def test_native_docker_connection():
    print("=" * 60)
    print("DOCKER NATIVE SOCKET TEST")
    print("=" * 60)

    socket_path = "/var/run/docker.sock"

    # Check socket exists
    if not os.path.exists(socket_path):
        print(f"❌ Socket not found: {socket_path}")
        return False

    print(f"✅ Socket exists: {socket_path}")

    # Check permissions
    st = os.stat(socket_path)
    print(f"✅ Permissions: {oct(st.st_mode)}")
    print(f"✅ Owner: UID={st.st_uid}, GID={st.st_gid}")
    print(f"✅ Current user: UID={os.getuid()}, GID={os.getgid()}")

    # Test raw socket connection
    try:
        print("\n🔍 Testing raw socket connection...")

        # Create unix socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)

        # Send HTTP request to Docker daemon
        request = "GET /version HTTP/1.1\r\nHost: localhost\r\n\r\n"
        sock.send(request.encode())

        # Read response
        response = sock.recv(4096).decode()
        sock.close()

        print("✅ Raw socket connection successful!")
        print(f"📋 Response preview: {response[:200]}...")

        # Parse JSON from response
        if "HTTP/1.1 200 OK" in response:
            json_start = response.find("{")
            if json_start != -1:
                json_data = response[json_start:]
                version_info = json.loads(json_data.split("\r\n\r\n")[1])
                print(f"✅ Docker version: {version_info.get('Version', 'Unknown')}")
                return True

        print("❌ Invalid response format")
        return False

    except Exception as e:
        print(f"❌ Raw socket failed: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = test_native_docker_connection()
    sys.exit(0 if success else 1)
