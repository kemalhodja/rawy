from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

# PostgreSQL için SSL gerekli (Render vb. için)
connect_args = {}
if settings.DATABASE_URL and settings.DATABASE_URL.startswith("postgresql"):
    connect_args["sslmode"] = "require"

# SQLite için check_same_thread=False
default_args = {"check_same_thread": False} if settings.DATABASE_URL and settings.DATABASE_URL.startswith("sqlite") else {}
connect_args.update(default_args)

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args if connect_args else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
