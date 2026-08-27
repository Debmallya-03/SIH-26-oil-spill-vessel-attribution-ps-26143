from app.core.config import settings


DATABASE_URL = settings.database_url


def get_database_url() -> str:
    return DATABASE_URL
