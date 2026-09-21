from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    future=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_database_schema(bind):
    """Add missing columns to existing SQLite databases created before the latest model schema."""
    inspector = inspect(bind)
    table_columns = {
        "notifications": {
            "notification_type": "VARCHAR(30) DEFAULT 'INFO'",
            "link": "VARCHAR(500)",
            "is_read": "BOOLEAN DEFAULT 0",
        },
        "support_tickets": {
            "attachment_url": "TEXT",
            "attachment_cloudinary_id": "VARCHAR(500)",
            "updated_at": "DATETIME",
        },
        "community_posts": {
            "image_cloudinary_url": "TEXT",
            "image_cloudinary_id": "VARCHAR(500)",
            "is_visible": "BOOLEAN DEFAULT 1",
            "updated_at": "DATETIME",
        },
        "products": {
            "product_type": "VARCHAR(100)",
            "target_crop": "VARCHAR(255)",
            "target_problem": "VARCHAR(255)",
            "usage_instructions": "TEXT",
            "safety_notes": "TEXT",
            "recommended_quantity": "VARCHAR(255)",
            "is_active": "BOOLEAN DEFAULT 1",
            "created_by": "VARCHAR(36)",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "activity_logs": {
            "occurred_at": "DATETIME",
        },
        "registration_requests": {
            "telegram_chat_id": "VARCHAR(100)",
        },
    }

    for table_name, required_columns in table_columns.items():
        if not inspector.has_table(table_name):
            if table_name in Base.metadata.tables:
                Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column_sql in required_columns.items():
            if column_name in existing_columns:
                continue
            with bind.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
