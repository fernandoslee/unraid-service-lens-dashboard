import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.main import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _mask_key(key: str) -> str:
    """Show only the last 4 characters of an API key."""
    if len(key) <= 4:
        return key
    return "\u2022" * 8 + key[-4:]


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    settings = get_settings()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "host": settings.unraid_host,
        "masked_key": _mask_key(settings.unraid_api_key) if settings.unraid_api_key else "",
        "verify_ssl": settings.unraid_verify_ssl,
        "error": None,
        "success": None,
    })


@router.post("/settings", response_class=HTMLResponse)
async def settings_submit(
    request: Request,
    host: str = Form(...),
    api_key: str = Form(""),
    verify_ssl: bool = Form(False),
):
    from unraid_api import UnraidClient
    from unraid_api.exceptions import (
        UnraidAuthenticationError,
        UnraidConnectionError,
        UnraidSSLError,
        UnraidTimeoutError,
    )

    from app.services.unraid import UnraidService

    settings = get_settings()

    # Use existing key if none provided
    effective_key = api_key.strip() if api_key.strip() else settings.unraid_api_key
    if not effective_key:
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "host": host,
            "masked_key": "",
            "verify_ssl": verify_ssl,
            "error": "API key is required.",
            "success": None,
        })

    # Test the connection
    error = None
    try:
        async with UnraidClient(host, effective_key, verify_ssl=verify_ssl) as client:
            connected = await client.test_connection()
            if not connected:
                error = "Connection test failed. Check host and API key."
    except UnraidAuthenticationError:
        error = "Authentication failed. Check your API key (requires ADMIN role)."
    except UnraidSSLError:
        error = "SSL certificate error. Try unchecking 'Verify SSL certificate'."
    except UnraidConnectionError as e:
        error = f"Could not connect to {host}. Is the server reachable? ({e})"
    except UnraidTimeoutError:
        error = f"Connection to {host} timed out."
    except Exception as e:
        error = f"Unexpected error: {e}"

    if error:
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "host": host,
            "masked_key": _mask_key(effective_key),
            "verify_ssl": verify_ssl,
            "error": error,
            "success": None,
        })

    # Save configuration
    data_dir = settings.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    env_path = data_dir / ".env"
    env_path.write_text(
        f"UNRAID_HOST={host}\n"
        f"UNRAID_API_KEY={effective_key}\n"
        f"UNRAID_VERIFY_SSL={'true' if verify_ssl else 'false'}\n"
    )
    env_path.chmod(0o600)

    # Clear cached settings and recreate client in-process
    get_settings.cache_clear()
    new_settings = get_settings()

    if new_settings.is_configured:
        new_client = UnraidClient(
            new_settings.unraid_host,
            new_settings.unraid_api_key,
            verify_ssl=new_settings.unraid_verify_ssl,
        )
        await new_client._create_session()

        old_client = getattr(request.app.state, "unraid_client", None)
        if old_client:
            await old_client.close()

        request.app.state.unraid_client = new_client
        request.app.state.unraid_service = UnraidService(
            new_client, new_settings.cache_ttl_seconds
        )
        logger.info("Reconnected to Unraid at %s via settings", host)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "host": host,
        "masked_key": _mask_key(effective_key),
        "verify_ssl": verify_ssl,
        "error": None,
        "success": "Connection successful. Settings saved.",
    })
