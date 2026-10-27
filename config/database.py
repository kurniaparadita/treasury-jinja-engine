from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from config.settings import settings
import logging

logger = logging.getLogger("Database")

_engine: Engine = None

def get_engine() -> Engine:
    """
    Singleton getter untuk SQLAlchemy Database Engine (Microsoft SQL Server via pyodbc).
    """
    global _engine
    if _engine is None:
        try:
            engine_kwargs = {
                "pool_pre_ping": True,
                "pool_size": 10,
                "max_overflow": 20,
                "connect_args": {"timeout": 3}
            }
            # fast_executemany hanya didukung oleh driver modern (ODBC Driver 11/13/17/18),
            # sedangkan driver legacy 'SQL Server' bawaan Windows tidak mendukungnya.
            if not settings.is_legacy_driver:
                engine_kwargs["fast_executemany"] = True

            _engine = create_engine(
                settings.database_url,
                **engine_kwargs
            )
            logger.info(
                f"SQL Server Engine terhubung ke: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} "
                f"menggunakan driver [{settings.DB_DRIVER}]"
            )
        except Exception as e:
            logger.error(f"Gagal menghubungkan ke Database SQL Server: {e}")
            raise e
    return _engine

def get_test_engine(sqlite_path: str = ":memory:") -> Engine:
    """Helper engine SQLite untuk pengujian mandiri tanpa database server."""
    return create_engine(f"sqlite:///{sqlite_path}")
