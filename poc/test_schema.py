"""
Investigate the Unraid GraphQL schema to find available container and VM fields.
"""

import asyncio
import os
import sys
import json


# Introspection query for DockerContainer type
CONTAINER_TYPE_QUERY = """
{
    __type(name: "DockerContainer") {
        name
        fields {
            name
            type {
                name
                kind
                ofType { name kind }
            }
        }
    }
}
"""

# Introspection query for VmDomain type
VM_TYPE_QUERY = """
{
    __type(name: "VmDomain") {
        name
        fields {
            name
            type {
                name
                kind
                ofType { name kind }
            }
        }
    }
}
"""

# Introspection for Plugin type
PLUGIN_TYPE_QUERY = """
{
    __type(name: "Plugin") {
        name
        fields {
            name
            type {
                name
                kind
                ofType { name kind }
            }
        }
    }
}
"""

# Test custom container query — start minimal then add fields
CONTAINER_BASIC_QUERY = """
query {
    docker {
        containers {
            id
            names
            state
        }
    }
}
"""

# Add webUiUrl
CONTAINER_WEBUI_QUERY = """
query {
    docker {
        containers {
            id
            names
            state
            webUiUrl
        }
    }
}
"""

# Add iconUrl
CONTAINER_ICON_QUERY = """
query {
    docker {
        containers {
            id
            names
            state
            iconUrl
        }
    }
}
"""

# Add isUpdateAvailable
CONTAINER_UPDATE_QUERY = """
query {
    docker {
        containers {
            id
            names
            state
            isUpdateAvailable
        }
    }
}
"""

# Full VM query with extra fields
VM_FULL_QUERY = """
query {
    vms {
        domains {
            id
            name
            state
            memory
            vcpu
            autostart
            iconUrl
            cpuMode
            primaryGpu
        }
    }
}
"""


async def main():
    from unraid_api import UnraidClient
    from unraid_api.exceptions import UnraidAPIError

    host = os.environ.get("UNRAID_HOST", "tower.local")
    api_key = os.environ.get("UNRAID_API_KEY", "")

    if not api_key:
        print("ERROR: UNRAID_API_KEY required")
        sys.exit(1)

    async with UnraidClient(host, api_key, verify_ssl=False) as client:

        # ── Schema introspection ────────────────────────────
        print("=" * 60)
        print("SCHEMA INTROSPECTION")
        print("=" * 60)

        for name, query in [
            ("DockerContainer", CONTAINER_TYPE_QUERY),
            ("VmDomain", VM_TYPE_QUERY),
            ("Plugin", PLUGIN_TYPE_QUERY),
        ]:
            print(f"\n--- {name} fields ---")
            try:
                result = await client.query(query)
                type_info = result.get("__type")
                if type_info and type_info.get("fields"):
                    for f in type_info["fields"]:
                        ftype = f["type"]
                        type_name = ftype.get("name") or (ftype.get("ofType", {}) or {}).get("name", "?")
                        kind = ftype.get("kind", "?")
                        print(f"  {f['name']}: {type_name} ({kind})")
                else:
                    print(f"  Type '{name}' not found or has no fields")
                    print(f"  Raw: {json.dumps(result, indent=2)[:500]}")
            except Exception as e:
                print(f"  ERROR: {e}")

        # ── Test custom queries one field at a time ─────────
        print("\n" + "=" * 60)
        print("TESTING CUSTOM CONTAINER QUERIES")
        print("=" * 60)

        tests = [
            ("basic (id, names, state)", CONTAINER_BASIC_QUERY),
            ("+ webUiUrl", CONTAINER_WEBUI_QUERY),
            ("+ iconUrl", CONTAINER_ICON_QUERY),
            ("+ isUpdateAvailable", CONTAINER_UPDATE_QUERY),
        ]

        for label, query in tests:
            print(f"\n--- {label} ---")
            try:
                result = await client.query(query)
                containers = result.get("docker", {}).get("containers", [])
                if containers:
                    c = containers[0]
                    print(f"  OK: Got {len(containers)} containers")
                    print(f"  First container fields: {list(c.keys())}")
                    # Show the tested field value
                    for key in ["webUiUrl", "iconUrl", "isUpdateAvailable"]:
                        if key in c:
                            print(f"  {key} = {c[key]}")
                else:
                    print(f"  OK but empty result")
            except UnraidAPIError as e:
                print(f"  FAIL: {e}")
                # Try to get more detail
                if hasattr(e, 'errors'):
                    for err in e.errors:
                        print(f"    GraphQL error: {err}")
            except Exception as e:
                print(f"  FAIL: {type(e).__name__}: {e}")

        # ── Test VM full query ──────────────────────────────
        print("\n" + "=" * 60)
        print("TESTING FULL VM QUERY")
        print("=" * 60)

        try:
            result = await client.query(VM_FULL_QUERY)
            domains = result.get("vms", {}).get("domains", [])
            if domains:
                print(f"OK: Got {len(domains)} VMs")
                for vm in domains:
                    print(f"\n  {vm.get('name')}:")
                    for k, v in vm.items():
                        print(f"    {k}: {v}")
            else:
                print("OK but no VMs returned")
        except UnraidAPIError as e:
            print(f"FAIL: {e}")
            if hasattr(e, 'errors'):
                for err in e.errors:
                    print(f"  GraphQL error: {err}")

            # Try fields one at a time
            print("\n  Trying VM fields individually...")
            base_fields = ["id", "name", "state"]
            extra_fields = ["memory", "vcpu", "autostart", "iconUrl", "cpuMode", "primaryGpu"]
            for field in extra_fields:
                fields_str = " ".join(base_fields + [field])
                q = f"query {{ vms {{ domains {{ {fields_str} }} }} }}"
                try:
                    result = await client.query(q)
                    domains = result.get("vms", {}).get("domains", [])
                    if domains:
                        val = domains[0].get(field)
                        print(f"    {field}: OK (value={val})")
                    else:
                        print(f"    {field}: OK (no VMs)")
                except Exception as ex:
                    print(f"    {field}: FAIL ({ex})")
        except Exception as e:
            print(f"FAIL: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
