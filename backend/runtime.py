"""Small runtime adapters that keep platform-specific behavior out of services."""

from __future__ import annotations

from backend.config import get_settings


class _WorkerSyncLock:
    """No-op sync lock used when the Worker entrypoint serializes each isolate."""

    def __enter__(self) -> _WorkerSyncLock:
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> bool:
        return False

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        return True

    def release(self) -> None:
        return None


def make_lock(*, reentrant: bool = False):
    """Use normal Python locks locally and rely on the Worker request gate there."""
    if get_settings().cloudflare_worker:
        return _WorkerSyncLock()

    from threading import Lock, RLock

    return RLock() if reentrant else Lock()
