# Service Lens

A lightweight, self-hosted dashboard for monitoring Docker containers and virtual machines on your Unraid server. Built for home lab enthusiasts who want a clean overview of their services without the complexity of full monitoring stacks.

## Why Service Lens?

Most home server dashboards either require manual configuration for every service or pull in heavyweight monitoring dependencies. Service Lens auto-discovers your Unraid services through the GraphQL API, resolves web UI URLs from Docker labels, and gives you a real-time dashboard — zero per-service configuration needed.

## Features

- **Auto-discovery** — Detects all Docker containers and VMs via the Unraid GraphQL API. No manual bookmarks or YAML configs.
- **Smart URL resolution** — Reads `net.unraid.docker.webui` labels and resolves `[IP]` / `[PORT:xxxx]` placeholders for bridge, macvlan, and container-mode networking.
- **Container logs** — View live container logs directly in the dashboard via the Docker socket. No SSH needed.
- **Real-time system metrics** — CPU, memory, temperature, and uptime at a glance. Auto-refreshes every 30 seconds.
- **Card and compact views** — Switch between visual cards with icons or a dense table view. Customize visible columns with drag-and-drop reordering.
- **Collapsible sections and filters** — Collapse Containers or VMs sections independently. Filter to show only running services. State persists across sessions.
- **First-run setup wizard** — Guided 2-step onboarding: create your account, then connect to Unraid. No config files to edit.
- **Session authentication** — Styled login page with bcrypt password hashing, configurable session duration, and rate-limited login attempts.
- **Dark theme** — Ships with a dark UI by default using Pico CSS. Light and system themes also available.

## Screenshots

> _Screenshots coming soon — the dashboard, compact view, setup wizard, and settings page._

## Quick Start

### Docker Compose (recommended)

```yaml
services:
  service-lens:
    image: ghcr.io/fernandoslee/service-lens:latest
    container_name: service-lens
    ports:
      - "8080:8080"
    volumes:
      - service-lens-data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped

volumes:
  service-lens-data:
```

```bash
docker compose up -d
```

Then open `http://<your-server-ip>:8080` and follow the setup wizard.

### Docker Run

```bash
docker run -d \
  --name service-lens \
  -p 8080:8080 \
  -v service-lens-data:/app/data \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  --restart unless-stopped \
  ghcr.io/fernandoslee/service-lens:latest
```

## Setup

On first launch, the setup wizard guides you through two steps:

1. **Create account** — Choose a username and password (minimum 8 characters). This protects access to the dashboard.
2. **Connect to Unraid** — Enter your Unraid server hostname (e.g., `tower.local`) and an API key.

### Generating an Unraid API Key

1. Open your Unraid web UI
2. Go to **Settings > Management Access > API Keys** (Unraid 7.x)
3. Create a new key with **Admin** role
4. Copy the key into the Service Lens setup wizard

### Docker Socket (for container logs)

Mount the Docker socket as a read-only volume to enable container log viewing:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

The container's entrypoint automatically detects the socket's group ID and configures permissions at runtime. No manual GID configuration needed.

## Configuration

All configuration is managed through the web UI (Settings page). Settings are persisted in `/app/data/.env` inside the container volume.

| Setting | Description | Default |
|---------|-------------|---------|
| Unraid Host | Server hostname or IP | _(set during setup)_ |
| API Key | Unraid GraphQL API key | _(set during setup)_ |
| Verify SSL | Validate Unraid's SSL certificate | `false` |
| Session Duration | How long login sessions last | 1 day |
| Default View | Card or compact table | Cards |
| Show Containers | Display containers section | `true` |
| Show VMs | Display VMs section | `true` |

You can also pass environment variables at container startup for initial configuration:

```yaml
environment:
  - UNRAID_HOST=tower.local
  - UNRAID_API_KEY=your-api-key
  - UNRAID_VERIFY_SSL=false
```

## Requirements

- **Unraid 7.x** with the GraphQL API enabled (built-in since Unraid 7.0)
- **Docker** on the host running Service Lens
- An **API key** with Admin role from your Unraid server

## Tech Stack

- **Backend**: Python 3.11 / FastAPI / Uvicorn
- **Frontend**: Jinja2 templates + HTMX + Pico CSS (no JavaScript build step)
- **Data source**: Unraid GraphQL API via [`unraid-api`](https://pypi.org/project/unraid-api/) Python library
- **Container logs**: Docker socket via [`docker-py`](https://pypi.org/project/docker/)

## Development

```bash
# Clone and set up
git clone https://github.com/fernandoslee/unraid-service-lens-dashboard.git
cd unraid-service-lens-dashboard
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run locally
UNRAID_HOST=tower.local UNRAID_API_KEY=<key> uvicorn app.main:app --port 8080

# Run tests
python -m pytest tests/ -q
```

### Building the Docker Image

```bash
docker compose build
docker compose up
```

## Security

- Passwords are hashed with **bcrypt** — plaintext passwords are never stored
- Login is **rate-limited** (10 attempts per 5-minute window)
- Session cookies use **signed cookies** with `SameSite=Lax`
- The Docker socket is mounted **read-only**
- The container runs as a **non-root user** (permissions handled automatically via entrypoint)
- Host input is validated against injection patterns
- `.env` writes are atomic (temp file + rename) to prevent corruption

## License

MIT
