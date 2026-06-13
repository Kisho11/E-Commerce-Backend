import warnings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings


def _resolve_engine():
    try:
        eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception:
        if settings.DEBUG:
            warnings.warn(
                "Primary database is unavailable in DEBUG mode; falling back to sqlite:///./dev.db.",
                RuntimeWarning,
                stacklevel=2,
            )
            return create_engine("sqlite:///./dev.db", connect_args={"check_same_thread": False})
        raise


engine = _resolve_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
