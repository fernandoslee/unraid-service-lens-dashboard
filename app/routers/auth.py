import logging

import bcrypt
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.main import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a hash. Handles both bcrypt and legacy plaintext."""
    if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    # Legacy plaintext — direct comparison
    return plain == hashed


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
    })


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    settings = get_settings()

    if not settings.is_auth_configured:
        return RedirectResponse(url="/", status_code=302)

    valid = (
        username == settings.auth_username
        and _verify_password(password, settings.auth_password)
    )

    if not valid:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password.",
        })

    # Migrate plaintext password to bcrypt on successful login
    if not settings.auth_password.startswith("$2b$"):
        from app.services.env_file import write_env
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        env_path = settings.data_dir / ".env"
        write_env(env_path, {"AUTH_PASSWORD": hashed})
        get_settings.cache_clear()
        logger.info("Migrated plaintext password to bcrypt hash")

    request.session["authenticated"] = True
    request.session["username"] = username
    logger.info("User '%s' logged in", username)
    return RedirectResponse(url="/", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
