import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Connect to database using DATABASE_URL from .env
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tpsodl.db")

# Normalize postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,
}

if "sqlite" in DATABASE_URL:
    connect_args["check_same_thread"] = False
    engine_kwargs["connect_args"] = connect_args
else:
    # PostgreSQL / Neon settings
    connect_args["connect_timeout"] = 30
    connect_args["keepalives"] = 1
    connect_args["keepalives_idle"] = 30
    connect_args["keepalives_interval"] = 10
    connect_args["keepalives_count"] = 5
    engine_kwargs["connect_args"] = connect_args
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_recycle"] = 60

engine = create_engine(DATABASE_URL, **engine_kwargs)
active_db_url = DATABASE_URL

if "sqlite" in active_db_url:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def sync_table_columns():
    """Applies column migrations if columns don't yet exist in the target database."""
    with engine.connect() as conn:
        # 1. vcr_masters subdivision
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE vcr_masters ADD COLUMN IF NOT EXISTS subdivision VARCHAR(100)"))
            else:
                conn.execute(text("ALTER TABLE vcr_masters ADD COLUMN subdivision VARCHAR(100)"))
            conn.commit()
        except Exception:
            pass

        # 2. daily_team_operations tl_name
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE daily_team_operations ADD COLUMN IF NOT EXISTS tl_name VARCHAR(100)"))
            else:
                conn.execute(text("ALTER TABLE daily_team_operations ADD COLUMN tl_name VARCHAR(100)"))
            conn.commit()
        except Exception:
            pass

        # 3. is_team_active
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE daily_team_operations ADD COLUMN IF NOT EXISTS is_team_active BOOLEAN DEFAULT TRUE"))
            else:
                conn.execute(text("ALTER TABLE daily_team_operations ADD COLUMN is_team_active BOOLEAN DEFAULT 1"))
            conn.commit()
        except Exception:
            pass

        # 4. operating_with_tl
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE daily_team_operations ADD COLUMN IF NOT EXISTS operating_with_tl BOOLEAN DEFAULT TRUE"))
            else:
                conn.execute(text("ALTER TABLE daily_team_operations ADD COLUMN operating_with_tl BOOLEAN DEFAULT 1"))
            conn.commit()
        except Exception:
            pass

        # 5. load_bookings page_no
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE load_bookings ADD COLUMN IF NOT EXISTS page_no VARCHAR(50)"))
            else:
                conn.execute(text("ALTER TABLE load_bookings ADD COLUMN page_no VARCHAR(50)"))
            conn.commit()
        except Exception:
            pass

        # 6. load_bookings book_number
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE load_bookings ADD COLUMN IF NOT EXISTS book_number VARCHAR(50)"))
            else:
                conn.execute(text("ALTER TABLE load_bookings ADD COLUMN book_number VARCHAR(50)"))
            conn.commit()
        except Exception:
            pass

        # 7. users circle length (ensure VARCHAR(255) for multi-circle assignment)
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE users ALTER COLUMN circle TYPE VARCHAR(255)"))
            conn.commit()
        except Exception:
            pass

        # 8. teams has_vehicle and is_office_team
        try:
            if "postgres" in active_db_url:
                conn.execute(text("ALTER TABLE teams ADD COLUMN IF NOT EXISTS has_vehicle BOOLEAN DEFAULT TRUE"))
                conn.execute(text("ALTER TABLE teams ADD COLUMN IF NOT EXISTS is_office_team BOOLEAN DEFAULT FALSE"))
            else:
                conn.execute(text("ALTER TABLE teams ADD COLUMN has_vehicle BOOLEAN DEFAULT 1"))
                conn.execute(text("ALTER TABLE teams ADD COLUMN is_office_team BOOLEAN DEFAULT 0"))
            conn.commit()
        except Exception:
            pass

    fix_postgres_sequences()

def fix_postgres_sequences():
    """Resets serial auto-increment sequences in Postgres to max(id) to avoid duplicate key errors."""
    if "postgres" not in active_db_url:
        return
    tables = [
        "users", "team_leads", "teams", "employees", "daily_team_operations",
        "attendance", "vehicle_log_books", "vcr_masters", "load_bookings",
        "disconnection_records", "collections"
    ]
    with engine.connect() as conn:
        for tbl in tables:
            try:
                sql = f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), COALESCE((SELECT MAX(id) + 1 FROM {tbl}), 1), false)"
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass

def reset_db():
    """Cleanly drops all tables and recreates them with fresh schema."""
    import models  # noqa: F401
    with engine.connect() as conn:
        if "postgres" in active_db_url:
            table_names = [
                "attendance", "daily_team_operations", "load_bookings",
                "disconnection_records", "vcr_masters", "collections",
                "vehicle_log_books", "employees", "teams", "team_leads", "users"
            ]
            for tbl in table_names:
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
                    conn.commit()
                except Exception:
                    pass
        else:
            Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def init_db(reset: bool = False):
    import models  # noqa: F401
    if reset:
        reset_db()
    else:
        Base.metadata.create_all(bind=engine)
        sync_table_columns()
