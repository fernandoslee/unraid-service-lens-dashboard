"""
Extract maximum available data from the Unraid GraphQL API.
Focus on what we CAN get, not what's missing.
"""

import asyncio
import os
import sys
import json


# Get ALL available container fields per the schema introspection
FULL_CONTAINER_QUERY = """
query {
    docker {
        containers {
            id
            names
            image
            imageId
            command
            created
            ports { ip privatePort publicPort type }
            sizeRootFs
            labels
            state
            status
            hostConfig { networkMode }
            networkSettings
            mounts
            autoStart
        }
    }
}
"""

# Get all available VM fields (only id, name, state per introspection)
VM_QUERY = """
query {
    vms {
        domains {
            id
            name
            state
        }
    }
}
"""

# System info queries
SYSTEM_QUERY = """
query {
    info {
        os { hostname platform distro release kernel arch }
        cpu { manufacturer brand cores threads speed }
        system { manufacturer model version uuid }
    }
}
"""

# Check what the top-level query fields are
SCHEMA_ROOT_QUERY = """
{
    __schema {
        queryType {
            fields {
                name
                type { name kind }
            }
        }
    }
}
"""

# Check if there are dockerMan templates or any other container metadata sources
DOCKER_NETWORKS_QUERY = """
query {
    docker {
        containers {
            id
            names
            state
            labels
            ports { ip privatePort publicPort type }
            hostConfig { networkMode }
        }
    }
}
"""


async def main():
    from unraid_api import UnraidClient

    host = os.environ.get("UNRAID_HOST", "tower.local")
    api_key = os.environ.get("UNRAID_API_KEY", "")

    async with UnraidClient(host, api_key, verify_ssl=False) as client:

        # ── Root schema fields ──────────────────────────────
        print("=" * 60)
        print("ROOT QUERY FIELDS (what top-level queries are available)")
        print("=" * 60)
        try:
            result = await client.query(SCHEMA_ROOT_QUERY)
            fields = result.get("__schema", {}).get("queryType", {}).get("fields", [])
            for f in sorted(fields, key=lambda x: x["name"]):
                ftype = f["type"]
                type_name = ftype.get("name", "?")
                print(f"  {f['name']}: {type_name} ({ftype.get('kind', '?')})")
        except Exception as e:
            print(f"ERROR: {e}")

        # ── Full container data ─────────────────────────────
        print("\n" + "=" * 60)
        print("FULL CONTAINER DATA (first 3 containers)")
        print("=" * 60)
        try:
            result = await client.query(FULL_CONTAINER_QUERY)
            containers = result.get("docker", {}).get("containers", [])
            # Show first 3 running containers for analysis
            running = [c for c in containers if c.get("state") == "RUNNING"]
            show = running[:3] if running else containers[:3]

            for c in show:
                name = c.get("names", ["?"])[0] if c.get("names") else "?"
                print(f"\n  --- {name} ---")
                print(f"    state: {c.get('state')}")
                print(f"    image: {c.get('image')}")
                print(f"    status: {c.get('status')}")

                # Ports - this is key for deriving web UI URLs
                ports = c.get("ports", [])
                if ports:
                    print(f"    ports:")
                    for p in ports:
                        print(f"      {p.get('publicPort', '?')} -> {p.get('privatePort', '?')}/{p.get('type', '?')}")
                else:
                    print(f"    ports: (none)")

                # Network mode
                hc = c.get("hostConfig", {})
                if hc:
                    print(f"    networkMode: {hc.get('networkMode', '?')}")

                # Labels - many Docker images use labels for metadata
                labels = c.get("labels", {})
                if labels:
                    # Show interesting labels (web UI related)
                    interesting_prefixes = [
                        "org.opencontainers",
                        "traefik",
                        "homepage",
                        "net.unraid",
                        "org.hotio",
                        "maintainer",
                    ]
                    print(f"    labels ({len(labels)} total):")
                    for k, v in sorted(labels.items()):
                        # Show all labels but truncate values
                        val_str = str(v)[:80]
                        print(f"      {k}: {val_str}")
                else:
                    print(f"    labels: (none)")

                # Network settings
                ns = c.get("networkSettings")
                if ns and isinstance(ns, dict):
                    networks = ns.get("Networks", {})
                    if networks:
                        print(f"    networks:")
                        for net_name, net_info in networks.items():
                            ip = net_info.get("IPAddress", "?") if isinstance(net_info, dict) else "?"
                            print(f"      {net_name}: {ip}")

        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

        # ── All containers summary ──────────────────────────
        print("\n" + "=" * 60)
        print("ALL CONTAINERS SUMMARY")
        print("=" * 60)
        try:
            result = await client.query(FULL_CONTAINER_QUERY)
            containers = result.get("docker", {}).get("containers", [])
            for c in containers:
                name = c.get("names", ["?"])[0] if c.get("names") else "?"
                state = c.get("state", "?")
                image = c.get("image", "?")
                ports = c.get("ports", [])
                web_ports = [p for p in ports if p.get("publicPort")]
                port_str = ", ".join(f"{p['publicPort']}" for p in web_ports) if web_ports else "no ports"
                network_mode = (c.get("hostConfig") or {}).get("networkMode", "?")
                print(f"  {name:25s} {state:8s} {network_mode:15s} ports=[{port_str}]  {image}")
        except Exception as e:
            print(f"ERROR: {e}")

        # ── VMs ─────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("VMs")
        print("=" * 60)
        try:
            result = await client.query(VM_QUERY)
            domains = result.get("vms", {}).get("domains", [])
            for vm in domains:
                print(f"  {vm.get('name', '?'):25s} state={vm.get('state', '?')}")
                print(f"    id: {vm.get('id')}")
        except Exception as e:
            print(f"ERROR: {e}")

        # ── System info via raw query ───────────────────────
        print("\n" + "=" * 60)
        print("SYSTEM INFO (raw query)")
        print("=" * 60)
        try:
            result = await client.query(SYSTEM_QUERY)
            print(json.dumps(result, indent=2)[:2000])
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(main())
