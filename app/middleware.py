from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Session-based auth. Redirects unauthenticated users to /login."""

    # Paths that never require auth
    PUBLIC_PATHS = {"/api/ping", "/login", "/logout"}
    # Paths that skip auth when app is not yet configured
    SETUP_PATHS = {"/setup", "/setup/credentials"}
    # Static files prefix
    STATIC_PREFIX = "/static/"

    def __init__(self, app, get_settings_fn):
        super().__init__(app)
        self._get_settings = get_settings_fn

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = self._get_settings()

        if not settings.is_auth_configured:
            return await call_next(request)

        path = request.url.path

        # Always allow public paths and static files
        if path in self.PUBLIC_PATHS or path.startswith(self.STATIC_PREFIX):
            return await call_next(request)

        # Allow setup when app is not configured
        if path in self.SETUP_PATHS and not settings.is_configured:
            return await call_next(request)

        # Check session
        if request.session.get("authenticated"):
            # Backfill username for sessions created before this field existed
            if "username" not in request.session:
                request.session["username"] = settings.auth_username
            return await call_next(request)

        return RedirectResponse(url="/login", status_code=302)
