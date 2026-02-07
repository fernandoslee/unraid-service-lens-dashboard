"""
POC: Validate Unraid GraphQL API data extraction.

Tests that we can retrieve all data needed for the Local Network Services Indexer:
- Docker containers (with webUiUrl, iconUrl, isUpdateAvailable)
- VMs (name, state, memory, vCPU)
- Plugins (name, version)
- System info (hostname, CPU, memory, uptime)

Usage:
    UNRAID_HOST=192.168.1.100 UNRAID_API_KEY=your-key python test_connection.py

    Or pass as arguments:
    python test_connection.py --host 192.168.1.100 --api-key your-key
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime


# Custom GraphQL query that requests fields the library's typed_get_containers() does NOT fetch
CONTAINERS_QUERY = """
query {
    docker {
        containers {
            id
            names
            image
            state
            status
            autoStart
            ports { ip privatePort publicPort type }
            webUiUrl
            iconUrl
            isUpdateAvailable
        }
    }
}
"""


def format_bytes(value: int | None) -> str:
    if value is None:
        return "N/A"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def format_uptime(boot_time: datetime | None) -> str:
    if boot_time is None:
        return "N/A"
    now = datetime.now(boot_time.tzinfo) if boot_time.tzinfo else datetime.now()
    delta = now - boot_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


def field_status(value, label: str = "") -> str:
    """Show a field value with a visual indicator of whether it's populated."""
    if value is None:
        return f"None  \u2190 MISSING"
    if isinstance(value, str) and not value:
        return f"''  \u2190 EMPTY"
    return str(value)


async def main(host: str, api_key: str, verify_ssl: bool = False):
    # Import here so we get a clear error if the library isn't installed
    try:
        from unraid_api import UnraidClient
        from unraid_api.exceptions import (
            UnraidAPIError,
            UnraidAuthenticationError,
            UnraidConnectionError,
            UnraidSSLError,
            UnraidTimeoutError,
        )
    except ImportError:
        print("ERROR: unraid-api package not installed.")
        print("Run: pip install unraid-api")
        sys.exit(1)

    print("=" * 60)
    print("LOCAL NETWORK SERVICES INDEXER - POC DATA EXTRACTION TEST")
    print("=" * 60)
    print(f"\nTarget: {host}")
    print(f"SSL Verify: {verify_ssl}")
    print()

    # ── 1. CONNECTION TEST ──────────────────────────────────────
    print("=" * 60)
    print("1. CONNECTION TEST")
    print("=" * 60)

    try:
        async with UnraidClient(host, api_key, verify_ssl=verify_ssl) as client:
            connected = await client.test_connection()
            if not connected:
                print("FAIL: test_connection() returned False")
                print("Check your host and API key.")
                return

            print("OK: Connected successfully")

            # Get version info
            try:
                version = await client.get_version()
                print(f"Unraid version: {version.get('unraid', 'unknown')}")
                print(f"API version: {version.get('api', 'unknown')}")
            except Exception as e:
                print(f"WARNING: Could not get version info: {e}")

            # ── 2. CONTAINERS (typed method) ────────────────────
            print()
            print("=" * 60)
            print("2. CONTAINERS via typed_get_containers()")
            print("   (Testing which fields the library populates)")
            print("=" * 60)

            try:
                typed_containers = await client.typed_get_containers()
                print(f"Found {len(typed_containers)} container(s)\n")

                for i, c in enumerate(typed_containers, 1):
                    print(f"  [{i}] {c.name}")
                    print(f"      state: {c.state} | image: {c.image}")
                    print(f"      status: {c.status}")
                    print(f"      webUiUrl: {field_status(c.webUiUrl)}")
                    print(f"      iconUrl: {field_status(c.iconUrl)}")
                    print(f"      isUpdateAvailable: {field_status(c.isUpdateAvailable)}")
                    print(f"      autoStart: {c.autoStart}")
                    ports_str = ", ".join(
                        f"{p.publicPort}->{p.privatePort}/{p.type}"
                        for p in (c.ports or [])
                    ) or "none"
                    print(f"      ports: [{ports_str}]")
                    print()
            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")

            # ── 3. CONTAINERS (custom query) ────────────────────
            print("=" * 60)
            print("3. CONTAINERS via custom GraphQL query")
            print("   (Testing webUiUrl, iconUrl, isUpdateAvailable)")
            print("=" * 60)

            try:
                raw = await client.query(CONTAINERS_QUERY)
                container_dicts = raw.get("docker", {}).get("containers", []) or []
                print(f"Found {len(container_dicts)} container(s)\n")

                # Try constructing DockerContainer models from raw data
                from unraid_api.models import DockerContainer

                for i, cd in enumerate(container_dicts, 1):
                    try:
                        c = DockerContainer.from_api_response(cd)
                        print(f"  [{i}] {c.name}")
                        print(f"      state: {c.state} | image: {c.image}")
                        print(f"      webUiUrl: {field_status(c.webUiUrl)}")
                        print(f"      iconUrl: {field_status(c.iconUrl)}")
                        print(f"      isUpdateAvailable: {field_status(c.isUpdateAvailable)}")
                        ports_str = ", ".join(
                            f"{p.publicPort}->{p.privatePort}/{p.type}"
                            for p in (c.ports or [])
                        ) or "none"
                        print(f"      ports: [{ports_str}]")
                    except Exception as e:
                        print(f"  [{i}] RAW (model parse failed: {e})")
                        print(f"      raw data: {cd}")
                    print()

                # Also show raw dict for first container for full inspection
                if container_dicts:
                    print("  --- Raw dict for first container (all fields): ---")
                    for k, v in container_dicts[0].items():
                        print(f"      {k}: {v}")
                    print()

            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")

            # ── 4. VIRTUAL MACHINES ─────────────────────────────
            print("=" * 60)
            print("4. VIRTUAL MACHINES via typed_get_vms()")
            print("=" * 60)

            try:
                vms = await client.typed_get_vms()
                print(f"Found {len(vms)} VM(s)\n")

                for i, vm in enumerate(vms, 1):
                    print(f"  [{i}] {vm.name}")
                    print(f"      state: {vm.state}")
                    print(f"      memory: {field_status(format_bytes(vm.memory) if vm.memory else None)}")
                    print(f"      vcpu: {field_status(vm.vcpu)}")
                    print(f"      autostart: {field_status(vm.autostart)}")
                    print(f"      iconUrl: {field_status(vm.iconUrl)}")
                    print(f"      cpuMode: {field_status(vm.cpuMode)}")
                    print()

                if not vms:
                    print("  (no VMs found)\n")

                # Also try raw dict method for comparison
                try:
                    raw_vms = await client.get_vms()
                    if raw_vms:
                        print("  --- Raw dict for first VM (all fields): ---")
                        for k, v in raw_vms[0].items():
                            print(f"      {k}: {v}")
                        print()
                except Exception as e:
                    print(f"  WARNING: get_vms() raw failed: {e}\n")

            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")

            # ── 5. PLUGINS ──────────────────────────────────────
            print("=" * 60)
            print("5. PLUGINS via typed_get_plugins()")
            print("=" * 60)

            try:
                plugins = await client.typed_get_plugins()
                print(f"Found {len(plugins)} plugin(s)\n")

                for i, p in enumerate(plugins, 1):
                    print(f"  [{i}] {p.name} v{p.version}")

                if not plugins:
                    print("  (no plugins found)")
                print()
            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")

            # ── 6. SYSTEM INFO ──────────────────────────────────
            print("=" * 60)
            print("6. SYSTEM INFO via get_server_info()")
            print("=" * 60)

            try:
                info = await client.get_server_info()
                print(f"  hostname: {field_status(info.hostname)}")
                print(f"  model: {field_status(info.model)}")
                print(f"  sw_version: {field_status(info.sw_version)}")
                print(f"  hw_version: {field_status(info.hw_version)}")
                print(f"  os_distro: {field_status(info.os_distro)}")
                print(f"  os_release: {field_status(info.os_release)}")
                print(f"  os_arch: {field_status(info.os_arch)}")
                print(f"  lan_ip: {field_status(info.lan_ip)}")
                print(f"  cpu_brand: {field_status(info.cpu_brand)}")
                print(f"  cpu_cores: {field_status(info.cpu_cores)}")
                print(f"  cpu_threads: {field_status(info.cpu_threads)}")
                print(f"  license_type: {field_status(info.license_type)}")
                print()
            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")

            # ── 7. SYSTEM METRICS ───────────────────────────────
            print("=" * 60)
            print("7. SYSTEM METRICS via get_system_metrics()")
            print("=" * 60)

            try:
                metrics = await client.get_system_metrics()
                print(f"  cpu_percent: {field_status(metrics.cpu_percent)}")
                print(f"  cpu_temperature: {field_status(metrics.cpu_temperature)}")
                print(f"  memory_percent: {field_status(metrics.memory_percent)}")
                print(f"  memory_total: {field_status(format_bytes(metrics.memory_total) if metrics.memory_total else None)}")
                print(f"  memory_used: {field_status(format_bytes(metrics.memory_used) if metrics.memory_used else None)}")
                print(f"  memory_free: {field_status(format_bytes(metrics.memory_free) if metrics.memory_free else None)}")
                print(f"  swap_percent: {field_status(metrics.swap_percent)}")
                print(f"  uptime: {field_status(format_uptime(metrics.uptime) if metrics.uptime else None)}")
                print()
            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")

            # ── SUMMARY ────────────────────────────────────────
            print("=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print()
            print("Check the output above for fields marked 'MISSING'.")
            print("Key questions answered:")
            print("  - Does typed_get_containers() populate webUiUrl? (check section 2)")
            print("  - Does our custom query populate webUiUrl? (check section 3)")
            print("  - What VM fields are available? (check section 4)")
            print("  - What system info is available? (check sections 6-7)")

    except UnraidAuthenticationError:
        print("FAIL: Authentication error. Check your API key.")
        print("Required role: ADMIN")
        print("Create one via: unraid-api apikey --create --name 'services-indexer' --roles ADMIN")
    except UnraidSSLError as e:
        print(f"FAIL: SSL certificate error: {e}")
        print("Try running with --no-verify-ssl")
    except UnraidConnectionError as e:
        print(f"FAIL: Connection error: {e}")
        print(f"Is the Unraid server reachable at {host}?")
    except UnraidTimeoutError:
        print(f"FAIL: Connection to {host} timed out.")
    except Exception as e:
        print(f"FAIL: Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Unraid API data extraction")
    parser.add_argument("--host", default=os.environ.get("UNRAID_HOST", ""),
                        help="Unraid server hostname or IP")
    parser.add_argument("--api-key", default=os.environ.get("UNRAID_API_KEY", ""),
                        help="Unraid API key")
    parser.add_argument("--no-verify-ssl", action="store_true", default=True,
                        help="Disable SSL certificate verification (default: disabled)")
    parser.add_argument("--verify-ssl", action="store_true",
                        help="Enable SSL certificate verification")

    args = parser.parse_args()

    if not args.host or not args.api_key:
        print("ERROR: Both --host and --api-key are required.")
        print("Set via arguments or UNRAID_HOST / UNRAID_API_KEY env vars.")
        print()
        parser.print_help()
        sys.exit(1)

    verify_ssl = args.verify_ssl and not args.no_verify_ssl

    asyncio.run(main(args.host, args.api_key, verify_ssl))
