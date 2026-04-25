import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse


try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


DB_PATH = Path(__file__).resolve().parent.parent / "fleetcare.db"


def _database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def _engine():
    database_url = _database_url()
    return "postgres" if database_url.startswith(("postgres://", "postgresql://")) else "sqlite"


class CursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class ConnectionWrapper:
    def __init__(self, connection, engine):
        self.connection = connection
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.connection.close()

    def execute(self, query, params=()):
        cursor = self.connection.cursor()
        cursor.execute(_rewrite_query(query, self.engine), params)
        return CursorWrapper(cursor)


def get_connection():
    engine = _engine()

    if engine == "postgres":
        if psycopg is None:
            raise RuntimeError(
                "DATABASE_URL is set for PostgreSQL, but psycopg is not installed. "
                "Install dependencies from requirements.txt."
            )

        parsed = urlparse(_database_url())
        connection = psycopg.connect(
            dbname=(parsed.path or "/")[1:],
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432,
            row_factory=dict_row,
            sslmode=os.environ.get("PGSSLMODE", "require"),
        )
        return ConnectionWrapper(connection, engine)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return ConnectionWrapper(connection, engine)


def init_db():
    with get_connection() as connection:
        for statement in schema_statements(connection.engine):
            connection.execute(statement)
        for statement in migration_statements(connection.engine):
            connection.execute(statement)


def schema_statements(engine):
    id_column = "BIGSERIAL PRIMARY KEY" if engine == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    integer_fk = "BIGINT" if engine == "postgres" else "INTEGER"
    real_type = "DOUBLE PRECISION" if engine == "postgres" else "REAL"
    timestamp_type = "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"

    return [
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id {id_column},
            company_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at {timestamp_type}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS vehicles (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            name TEXT NOT NULL,
            plate TEXT NOT NULL,
            model TEXT,
            year INTEGER,
            odometer INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Active',
            created_at {timestamp_type},
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS drivers (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            name TEXT NOT NULL,
            license_number TEXT,
            phone TEXT,
            email TEXT,
            status TEXT NOT NULL DEFAULT 'Active',
            created_at {timestamp_type},
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS assignments (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            vehicle_id {integer_fk} NOT NULL,
            driver_id {integer_fk} NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at {timestamp_type},
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY(driver_id) REFERENCES drivers(id) ON DELETE CASCADE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS maintenance_logs (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            vehicle_id {integer_fk} NOT NULL,
            service_type TEXT NOT NULL,
            service_date TEXT NOT NULL,
            odometer INTEGER NOT NULL,
            cost {real_type} NOT NULL,
            notes TEXT,
            next_due_date TEXT,
            next_due_odometer INTEGER,
            created_at {timestamp_type},
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS fuel_logs (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            vehicle_id {integer_fk} NOT NULL,
            fill_date TEXT NOT NULL,
            odometer INTEGER NOT NULL,
            liters {real_type} NOT NULL,
            total_cost {real_type} NOT NULL,
            price_per_liter {real_type} NOT NULL,
            station TEXT,
            full_tank INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at {timestamp_type},
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS reminders (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            vehicle_id {integer_fk} NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT,
            due_odometer INTEGER,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at {timestamp_type},
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS trips (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            vehicle_id {integer_fk} NOT NULL,
            label TEXT,
            start_latitude {real_type},
            start_longitude {real_type},
            end_latitude {real_type},
            end_longitude {real_type},
            status TEXT NOT NULL DEFAULT 'Active',
            started_at {timestamp_type},
            ended_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS gps_logs (
            id {id_column},
            user_id {integer_fk} NOT NULL,
            vehicle_id {integer_fk} NOT NULL,
            trip_id {integer_fk},
            latitude {real_type} NOT NULL,
            longitude {real_type} NOT NULL,
            accuracy_meters {real_type},
            created_at {timestamp_type},
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE SET NULL
        )
        """,
    ]


def migration_statements(engine):
    trip_id_column = "BIGSERIAL PRIMARY KEY" if engine == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    integer_fk = "BIGINT" if engine == "postgres" else "INTEGER"
    real_type = "DOUBLE PRECISION" if engine == "postgres" else "REAL"
    timestamp_type = "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"

    return [
        "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS photo_name TEXT",
        "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS photo_data TEXT",
        "ALTER TABLE maintenance_logs ADD COLUMN IF NOT EXISTS attachment_name TEXT",
        "ALTER TABLE maintenance_logs ADD COLUMN IF NOT EXISTS attachment_data TEXT",
        f"""
        CREATE TABLE IF NOT EXISTS trips (
            id {trip_id_column},
            user_id {integer_fk} NOT NULL,
            vehicle_id {integer_fk} NOT NULL,
            label TEXT,
            start_latitude {real_type},
            start_longitude {real_type},
            end_latitude {real_type},
            end_longitude {real_type},
            status TEXT NOT NULL DEFAULT 'Active',
            started_at {timestamp_type},
            ended_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        )
        """,
        f"ALTER TABLE gps_logs ADD COLUMN IF NOT EXISTS trip_id {integer_fk}",
    ]


def _rewrite_query(query, engine):
    if engine == "sqlite":
        return query

    pieces = []
    in_single_quote = False
    for char in query:
        if char == "'":
            in_single_quote = not in_single_quote
            pieces.append(char)
        elif char == "?" and not in_single_quote:
            pieces.append("%s")
        else:
            pieces.append(char)
    return "".join(pieces)
