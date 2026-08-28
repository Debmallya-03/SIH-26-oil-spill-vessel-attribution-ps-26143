from app.db.connection import check_database_status, get_database_target, get_database_url


try:
    DATABASE_URL = get_database_url()
except Exception:
    DATABASE_URL = None

__all__ = ["DATABASE_URL", "check_database_status", "get_database_target", "get_database_url"]
