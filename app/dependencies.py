from fastapi import Request

from app.services.unraid import UnraidService


def is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def get_unraid_service(request: Request) -> UnraidService | None:
    return getattr(request.app.state, "unraid_service", None)
