import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.docker import DockerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("unraid_api").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.is_configured:
        from unraid_api import UnraidClient

        from app.services.unraid import UnraidService

        client = UnraidClient(
            settings.unraid_host,
            settings.unraid_api_key,
            verify_ssl=settings.unraid_verify_ssl,
        )
        await client._create_session()
        app.state.unraid_client = client
        app.state.unraid_service = UnraidService(client, settings.cache_ttl_seconds, server_host=settings.unraid_host)
        logging.info("Connected to Unraid at %s", settings.unraid_host)
    else:
        app.state.unraid_client = None
        app.state.unraid_service = None
        logging.info("No Unraid connection configured — setup required")
    # Docker socket for container logs
    docker_service = DockerService.create()
    app.state.docker_service = docker_service
    yield
    if docker_service is not None:
        docker_service.close()
    if getattr(app.state, "unraid_client", None) is not None:
        await app.state.unraid_client.close()


app = FastAPI(title="Unraid Service Lens Dashboard", lifespan=lifespan)

import secrets  # noqa: E402

from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from app.middleware import SessionAuthMiddleware  # noqa: E402

# Session auth middleware (checks session, redirects to /login)
app.add_middleware(SessionAuthMiddleware, get_settings_fn=get_settings)

# Starlette session middleware (signed cookie)
_settings = get_settings()
_secret = _settings.session_secret_key or secrets.token_hex(32)
if not _settings.session_secret_key:
    logging.getLogger(__name__).warning(
        "No SESSION_SECRET_KEY configured — using ephemeral key (sessions lost on restart)"
    )
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret,
    max_age=_settings.session_max_age,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


# Jinja2 custom filters
def format_bytes(value: int | None) -> str:
    if value is None:
        return "N/A"
    v = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(v) < 1024:
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} PB"


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


templates.env.filters["format_bytes"] = format_bytes
templates.env.filters["format_uptime"] = format_uptime

from app.routers import api, auth, dashboard, settings, setup  # noqa: E402

app.include_router(dashboard.router)
app.include_router(api.router)
app.include_router(setup.router)
app.include_router(settings.router)
app.include_router(auth.router)
