"""Compatibility imports for the original database module layout."""

from backend.database import Base, SessionLocal, engine, get_db, initialize_database

__all__ = ["Base", "SessionLocal", "engine", "get_db", "initialize_database"]
