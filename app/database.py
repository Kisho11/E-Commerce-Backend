import warnings
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings


def create_sqlalchemy_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def resolve_engine():
    primary_engine = create_sqlalchemy_engine(settings.DATABASE_URL)

    if not settings.DEBUG:
        return primary_engine

    try:
        with primary_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return primary_engine
    except SQLAlchemyError as primary_error:
        fallback_url = settings.DEV_DATABASE_FALLBACK_URL
        if not fallback_url or fallback_url == settings.DATABASE_URL:
            raise primary_error

        fallback_engine = create_sqlalchemy_engine(fallback_url)
        try:
            with fallback_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise primary_error

        warnings.warn(
            (
                "Primary database is unavailable in DEBUG mode; "
                f"falling back to {fallback_url}."
            ),
            RuntimeWarning,
            stacklevel=2,
        )
        return fallback_engine


engine = resolve_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
