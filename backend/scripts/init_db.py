import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.connection import DatabaseUnavailableError
from app.db.connection import get_database_target
from app.db.migrations import initialize_database


def main() -> None:
    target = get_database_target()
    print(
        "Database connection target: "
        f"host={target['host']} "
        f"port={target['port']} "
        f"database={target['database']} "
        f"user={target['user']}"
    )
    try:
        initialize_database()
    except DatabaseUnavailableError as exc:
        raise SystemExit(f"Database unavailable: {exc}") from exc
    print("Database initialized with PostGIS extension and Day-5 incident tables.")


if __name__ == "__main__":
    main()
