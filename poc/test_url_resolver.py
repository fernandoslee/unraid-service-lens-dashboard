"""
POC: Resolve web UI URLs from Unraid Docker labels.

The `net.unraid.docker.webui` label contains URL templates like:
  http://[IP]:[PORT:7878]/system/status

This script resolves these templates using:
  - [IP] → the Unraid server's LAN IP
  - [PORT:xxxx] → the mapped public port for the given private port

Complications:
  - Containers using `container:<id>` network mode (e.g., through a VPN container)
    don't have their own ports — their ports are on the VPN container
  - Containers using `br0` (macvlan) network have their own IP, no port mapping needed
  - Containers using `bridge` have standard port mappings
"""

import asyncio
import os
import re
import sys


CONTAINER_QUERY = """
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
            labels
            hostConfig { networkMode }
            networkSettings
        }
    }
}
"""


def resolve_webui_url(
    webui_template: str,
    server_ip: str,
    container_ip: str | None,
    ports: list[dict],
    network_mode: str,
) -> str | None:
    """
    Resolve a net.unraid.docker.webui template to an actual URL.

    Templates use:
      [IP]          → server IP (bridge/container mode) or container IP (macvlan)
      [PORT:xxxx]   → mapped public port for private port xxxx
    """
    if not webui_template:
        return None

    url = webui_template

    # Determine the IP to use
    if network_mode.startswith("br"):
        # macvlan/ipvlan — container has its own IP on the LAN
        ip = container_ip or server_ip
    else:
        ip = server_ip

    url = url.replace("[IP]", ip)

    # Resolve [PORT:xxxx] patterns
    def replace_port(match):
        private_port = int(match.group(1))
        # Look for a public port mapping for this private port
        for p in ports:
            if p.get("privatePort") == private_port and p.get("publicPort"):
                return str(p["publicPort"])
        # No mapping found — use the private port as-is
        # (works for macvlan/host network where ports aren't mapped)
        return str(private_port)

    url = re.sub(r"\[PORT:(\d+)\]", replace_port, url)

    return url


async def main():
    from unraid_api import UnraidClient

    host = os.environ.get("UNRAID_HOST", "tower.local")
    api_key = os.environ.get("UNRAID_API_KEY", "")

    async with UnraidClient(host, api_key, verify_ssl=False) as client:
        # Get server IP
        info = await client.get_server_info()
        server_ip = info.lan_ip or host
        print(f"Server IP: {server_ip}\n")

        # Get containers
        result = await client.query(CONTAINER_QUERY)
        containers = result.get("docker", {}).get("containers", [])

        # Build a lookup of container ID → container (for resolving container:xxx networking)
        id_to_container = {}
        for c in containers:
            cid = c.get("id", "")
            # The id is prefixed like "container:xxxxx"
            # The networkMode references the raw Docker ID, so also store by the Docker ID part
            if ":" in cid:
                docker_id = cid.split(":", 1)[1]
                id_to_container[docker_id] = c
            # Also try matching by full long IDs from the names
            for name in c.get("names", []):
                id_to_container[name.lstrip("/")] = c

        print("=" * 80)
        print("RESOLVED WEB UI URLs")
        print("=" * 80)

        for c in containers:
            name = c.get("names", ["?"])[0].lstrip("/")
            state = c.get("state", "?")
            labels = c.get("labels") or {}
            ports = c.get("ports") or []
            network_mode = (c.get("hostConfig") or {}).get("networkMode", "bridge")

            webui_template = labels.get("net.unraid.docker.webui", "")
            icon_url = labels.get("net.unraid.docker.icon", "")

            # Get container's own IP (for macvlan)
            container_ip = None
            ns = c.get("networkSettings")
            if ns and isinstance(ns, dict):
                networks = ns.get("Networks", {})
                for net_name, net_info in networks.items():
                    if isinstance(net_info, dict) and net_info.get("IPAddress"):
                        container_ip = net_info["IPAddress"]
                        break

            # For containers using container:xxx networking, get ports from the parent
            effective_ports = ports
            if network_mode.startswith("container:"):
                parent_id = network_mode.split(":", 1)[1]
                parent = id_to_container.get(parent_id)
                if parent:
                    parent_name = parent.get("names", ["?"])[0].lstrip("/")
                    effective_ports = parent.get("ports") or []
                else:
                    parent_name = f"unknown ({parent_id[:12]})"

            resolved_url = resolve_webui_url(
                webui_template, server_ip, container_ip, effective_ports, network_mode
            )

            # Print results
            print(f"\n  {name:25s} [{state}]")
            print(f"    network: {network_mode[:50]}")
            if container_ip:
                print(f"    container_ip: {container_ip}")
            if webui_template:
                print(f"    template: {webui_template}")
                print(f"    resolved: {resolved_url}")
            else:
                print(f"    webui: (no template in labels)")
            if icon_url:
                print(f"    icon: {icon_url[:80]}...")
            if effective_ports and effective_ports != ports:
                print(f"    ports (from parent): {[(p.get('publicPort'), p.get('privatePort')) for p in effective_ports]}")

        # ── Summary table ───────────────────────────────────
        print("\n" + "=" * 80)
        print("SUMMARY: Services with Web UI")
        print("=" * 80)
        print(f"  {'Name':25s} {'State':8s} {'Web UI URL'}")
        print(f"  {'-'*25} {'-'*8} {'-'*40}")

        for c in containers:
            name = c.get("names", ["?"])[0].lstrip("/")
            state = c.get("state", "?")
            labels = c.get("labels") or {}
            ports = c.get("ports") or []
            network_mode = (c.get("hostConfig") or {}).get("networkMode", "bridge")
            webui_template = labels.get("net.unraid.docker.webui", "")

            if not webui_template:
                continue

            container_ip = None
            ns = c.get("networkSettings")
            if ns and isinstance(ns, dict):
                for net_info in (ns.get("Networks") or {}).values():
                    if isinstance(net_info, dict) and net_info.get("IPAddress"):
                        container_ip = net_info["IPAddress"]
                        break

            effective_ports = ports
            if network_mode.startswith("container:"):
                parent_id = network_mode.split(":", 1)[1]
                parent = id_to_container.get(parent_id)
                if parent:
                    effective_ports = parent.get("ports") or []

            resolved = resolve_webui_url(
                webui_template, server_ip, container_ip, effective_ports, network_mode
            )
            print(f"  {name:25s} {state:8s} {resolved or '(unresolvable)'}")


if __name__ == "__main__":
    asyncio.run(main())
