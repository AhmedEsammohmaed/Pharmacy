"""Cloudflare Python Worker entrypoint for the existing FastAPI application."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy.engine import URL
from workers import WorkerEntrypoint, asgi

_APPLICATION = None
_WORKER_REQUEST_LOCK = asyncio.Lock()


def _binding_value(env, key: str, default: str = "") -> str:
    try:
        value = getattr(env, key)
    except Exception:
        return default
    if value is None:
        return default
    return str(value)


def _configure_environment(env) -> None:
    hyperdrive = env.HYPERDRIVE
    database_url = URL.create(
        "postgresql+pg8000",
        username=_binding_value(hyperdrive, "user"),
        password=_binding_value(hyperdrive, "password"),
        host=_binding_value(hyperdrive, "host"),
        port=int(_binding_value(hyperdrive, "port", "5432")),
        database=_binding_value(hyperdrive, "database"),
    )
    os.environ.update(
        {
            "DATABASE_URL": database_url.render_as_string(hide_password=False),
            "CLOUDFLARE_WORKER": "true",
            "ENVIRONMENT": _binding_value(env, "ENVIRONMENT", "production"),
            "COOKIE_SECURE": _binding_value(env, "COOKIE_SECURE", "true"),
            "BUSINESS_TIMEZONE": _binding_value(env, "BUSINESS_TIMEZONE", "Africa/Cairo"),
            "CHAT_PROVIDER": _binding_value(env, "CHAT_PROVIDER", "gemini"),
            "CHAT_MODEL_ID": _binding_value(env, "CHAT_MODEL_ID", "gemini-3.8-flash"),
            "CHAT_MAX_OUTPUT_TOKENS": _binding_value(env, "CHAT_MAX_OUTPUT_TOKENS", "1800"),
        }
    )
    for key in (
        "APP_NAME",
        "GEMINI_API_KEY",
        "N8N_CHAT_WEBHOOK_URL",
        "N8N_CHAT_WEBHOOK_TOKEN",
    ):
        value = _binding_value(env, key)
        if value:
            os.environ[key] = value


def _get_application(env):
    global _APPLICATION
    if _APPLICATION is not None:
        return _APPLICATION

    _configure_environment(env)
    from backend.database import SessionLocal, get_db
    from backend.main import app

    async def worker_database_session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    # Avoid AnyIO's thread-backed dependency executor in the Python Worker runtime.
    app.dependency_overrides[get_db] = worker_database_session
    _APPLICATION = app
    return app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        async with _WORKER_REQUEST_LOCK:
            app = _get_application(self.env)
            return await asgi.fetch(app, request.js_object, self.env)

    async def scheduled(self, controller, env, ctx):
        async with _WORKER_REQUEST_LOCK:
            _get_application(env)
            from backend.services.automation_service import run_daily_automations

            run_daily_automations()
