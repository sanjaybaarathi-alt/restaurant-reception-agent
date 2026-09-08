"""SQLAlchemy engine, session factory, and FastAPI dependency."""
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://restaurant:restaurant@localhost:5432/restaurant",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
