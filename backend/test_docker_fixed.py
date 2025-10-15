#!/usr/bin/env python3
"""
Docker Connection Test - Fixed Version
"""
import os
import sys
import docker


def clear_docker_env():
    """Clear all Docker environment variables"""
    docker_vars = [
        "DOCKER_HOST",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "DOCKER_MACHINE_NAME",
    ]
    old_vars = {}

    for var in docker_vars:
        if var in os.environ:
            old_vars[var] = os.environ[var]
            del os.environ[var]
            print(f"   Cleared {var}")

    return old_vars


def restore_docker_env(old_vars):
    """Restore Docker environment variables"""
    for var, value in old_vars.items():
        os.environ[var] = value


def test_docker_connection():
    print("=" * 60)
    print("DOCKER CONNECTIVITY DIAGNOSTIC - FIXED VERSION")
    print("=" * 60)

    # Check socket
    socket_path = "/var/run/docker.sock"
    print(f"\n1. Checking Docker socket: {socket_path}")
    if os.path.exists(socket_path):
        print(f"   ✅ Socket exists")
        st = os.stat(socket_path)
        print(f"   Permissions: {oct(st.st_mode)}")
        print(f"   Owner: UID={st.st_uid}, GID={st.st_gid}")
    else:
        print(f"   ❌ Socket NOT found!")
        return False

    # Check environment
    print(f"\n2. Environment variables:")
    print(f"   DOCKER_HOST: {os.environ.get('DOCKER_HOST', 'Not set')}")
    print(f"   Current UID: {os.getuid()}")
    print(f"   Current GID: {os.getgid()}")

    # Test Method 1: Clean environment + from_env()
    print(f"\n3. Testing with CLEAN environment...")
    old_vars = clear_docker_env()

    try:
        print("   Attempting docker.from_env()...")
        client = docker.from_env()
        version = client.version()
        print(f"   ✅ SUCCESS! Docker version: {version['Version']}")
        restore_docker_env(old_vars)
        return True
    except Exception as e:
        print(f"   ❌ docker.from_env() FAILED: {type(e).__name__}: {e}")

    # Test Method 2: Direct unix socket
    print(f"\n4. Testing direct unix socket...")
    try:
        client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
        client.ping()
        version = client.version()
        print(f"   ✅ SUCCESS! Docker version: {version['Version']}")
        restore_docker_env(old_vars)
        return True
    except Exception as e:
        print(f"   ❌ Direct unix socket FAILED: {type(e).__name__}: {e}")

    # Test Method 3: API Client
    print(f"\n5. Testing APIClient...")
    try:
        api = docker.APIClient(base_url="unix:///var/run/docker.sock")
        api.ping()
        version = api.version()
        print(f"   ✅ SUCCESS! Docker version: {version['Version']}")
        restore_docker_env(old_vars)
        return True
    except Exception as e:
        print(f"   ❌ APIClient FAILED: {type(e).__name__}: {e}")

    restore_docker_env(old_vars)
    print("\n" + "=" * 60)
    print("❌ ALL METHODS FAILED")
    print("=" * 60)
    return False


if __name__ == "__main__":
    success = test_docker_connection()
    sys.exit(0 if success else 1)
