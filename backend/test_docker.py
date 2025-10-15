#!/usr/bin/env python3
"""
Docker connectivity diagnostic script
Run this inside the backend container to diagnose Docker access issues
"""

import docker
import os
import sys


def test_docker_connection():
    print("=" * 60)
    print("DOCKER CONNECTIVITY DIAGNOSTIC")
    print("=" * 60)

    # Check socket
    socket_path = "/var/run/docker.sock"
    print(f"\n1. Checking Docker socket: {socket_path}")
    if os.path.exists(socket_path):
        print(f"   ✅ Socket exists")
        try:
            st = os.stat(socket_path)
            print(f"   Permissions: {oct(st.st_mode)}")
            print(f"   Owner: UID={st.st_uid}, GID={st.st_gid}")
        except Exception as e:
            print(f"   ⚠️  Cannot stat: {e}")
    else:
        print(f"   ❌ Socket NOT found!")
        return False

    # Check environment
    print(f"\n2. Environment variables:")
    print(f"   DOCKER_HOST: {os.environ.get('DOCKER_HOST', 'Not set')}")
    print(f"   Current UID: {os.getuid()}")
    print(f"   Current GID: {os.getgid()}")

    # Test Method 1: from_env()
    print(f"\n3. Testing docker.from_env()...")
    old_docker_host = os.environ.get("DOCKER_HOST")
    try:
        if "DOCKER_HOST" in os.environ:
            del os.environ["DOCKER_HOST"]
            print("   Removed DOCKER_HOST env var")

        client = docker.from_env()
        version = client.version()
        print(f"   ✅ SUCCESS! Docker {version['Version']}")
        print(f"   API Version: {version['ApiVersion']}")
        return True
    except Exception as e:
        print(f"   ❌ FAILED: {type(e).__name__}")
        print(f"   Error: {e}")
    finally:
        if old_docker_host:
            os.environ["DOCKER_HOST"] = old_docker_host

    # Test Method 2: Direct unix socket
    print(f"\n4. Testing DockerClient with unix socket...")
    try:
        client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
        client.ping()
        version = client.version()
        print(f"   ✅ SUCCESS! Docker {version['Version']}")
        return True
    except Exception as e:
        print(f"   ❌ FAILED: {type(e).__name__}")
        print(f"   Error: {e}")

    # Test Method 3: API Client
    print(f"\n5. Testing APIClient...")
    try:
        api = docker.APIClient(base_url="unix:///var/run/docker.sock")
        api.ping()
        print(f"   ✅ API ping successful!")
        return True
    except Exception as e:
        print(f"   ❌ FAILED: {type(e).__name__}")
        print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print("❌ ALL METHODS FAILED")
    print("=" * 60)
    return False


if __name__ == "__main__":
    success = test_docker_connection()
    sys.exit(0 if success else 1)
