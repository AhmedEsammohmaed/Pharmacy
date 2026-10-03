import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from typing import AsyncIterator
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend import models  # noqa: F401 - registers mapped models with Base.metadata.
from backend.automations import router as automation_router
from backend.auth import get_current_user, router as auth_router
from backend.analytics import router as analytics_router
from backend.chat import router as chat_router
from backend.config import get_settings
from backend.database import engine, initialize_database
from backend.inventory import router as inventory_router
from backend.n8n_tools import router as n8n_tools_router
from backend.products import router as products_router
from backend.purchases import router as purchases_router
from backend.sales import router as sales_router
from backend.suppliers import router as suppliers_router
from backend.services.automation_service import run_daily_automations

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend"
logger = logging.getLogger(__name__)


async def _daily_automation_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_daily_automations)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled pharmacy automation run failed.")
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.cloudflare_worker:
        # Python Workers execute the ASGI lifespan around individual fetches.
        # Schema setup is a one-time deployment step; Cron handles automation.
        yield
        return

    initialize_database()
    automation_task = asyncio.create_task(_daily_automation_loop())
    try:
        yield
    finally:
        automation_task.cancel()
        try:
            await automation_task
        except asyncio.CancelledError:
            pass


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Pharmacy operations workspace and API.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

if not settings.cloudflare_worker:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(auth_router)
protected_api = {"prefix": "/api/v1", "dependencies": [Depends(get_current_user)]}
app.include_router(products_router, **protected_api)
app.include_router(inventory_router, **protected_api)
app.include_router(sales_router, **protected_api)
app.include_router(suppliers_router, **protected_api)
app.include_router(purchases_router, **protected_api)
app.include_router(analytics_router, **protected_api)
app.include_router(chat_router, **protected_api)
app.include_router(automation_router, **protected_api)
# This endpoint verifies a short-lived signed pharmacy capability instead of a browser session.
app.include_router(n8n_tools_router, prefix="/api/v1")
_auth_requests: dict[str, list[float]] = {}
_auth_rate_limits = {
    "/auth/login": (10, 15 * 60),
    "/auth/signup": (5, 60 * 60),
}


@app.middleware("http")
async def browser_security(request, call_next):
    global _auth_requests

    limit = _auth_rate_limits.get(request.url.path)
    if request.method == "POST" and limit:
        remote_address = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{remote_address}"
        now = monotonic()
        max_requests, window_seconds = limit
        attempts = [
            attempted_at
            for attempted_at in _auth_requests.get(key, [])
            if now - attempted_at < window_seconds
        ]
        if len(attempts) >= max_requests:
            retry_after = max(1, int(window_seconds - (now - attempts[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many account attempts. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )
        attempts.append(now)
        _auth_requests[key] = attempts
        if len(_auth_requests) > 2048:
            excess = len(_auth_requests) - 2048
            for old_key in list(_auth_requests)[:excess]:
                _auth_requests.pop(old_key, None)

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        host = request.headers.get("host", "").casefold()
        fetch_site = request.headers.get("sec-fetch-site", "").casefold()
        if origin and urlsplit(origin).netloc.casefold() != host:
            return JSONResponse(status_code=403, content={"detail": "Request origin is not allowed."})
        if fetch_site == "cross-site":
            return JSONResponse(status_code=403, content={"detail": "Cross-site request is not allowed."})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path == "/docs":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
    if request.url.path.startswith(("/auth/", "/api/v1/")):
        response.headers["Cache-Control"] = "no-store"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


if settings.cloudflare_worker:

    async def _worker_asset(path: str, request: Request) -> Response:
        from urllib.parse import quote

        env = request.scope.get("env")
        assets = getattr(env, "ASSETS", None) if env is not None else None
        if assets is None:
            return JSONResponse(status_code=503, content={"detail": "Static assets are not configured."})

        if path.startswith("static/"):
            path = path[len("static/") :]
        if not path:
            path = "index.html"
        if path.startswith(("api/", "auth/")):
            return JSONResponse(status_code=404, content={"detail": "Not found."})

        asset_url = f"https://assets.local/{quote(path, safe='/@-._~')}"
        result = await assets.fetch(asset_url)
        return Response(
            content=await result.bytes(),
            status_code=result.status,
            headers=result.headers,
        )

    @app.get("/", include_in_schema=False)
    async def pharmacy_workspace(request: Request) -> Response:
        return await _worker_asset("index.html", request)

else:

    @app.get("/", include_in_schema=False)
    def pharmacy_workspace() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}


if settings.cloudflare_worker:

    @app.get("/{path:path}", include_in_schema=False)
    async def cloudflare_static_asset(path: str, request: Request) -> Response:
        return await _worker_asset(path, request)
