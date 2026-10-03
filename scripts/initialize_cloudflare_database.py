"""Create or safely update the Cloudflare deployment's PostgreSQL schema."""

from backend.config import get_settings
from backend.database import initialize_database
from backend import models  # noqa: F401 - register ORM tables before schema creation.


def main() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        raise SystemExit(
            "Set DATABASE_URL to the new remote PostgreSQL database before initializing it."
        )
    initialize_database()
    print("PostgreSQL schema is ready for the Cloudflare Worker.")


if __name__ == "__main__":
    main()
