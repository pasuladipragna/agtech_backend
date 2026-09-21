import sqlite3

def migrate_users():
    conn = sqlite3.connect("smart_agritech.db")
    cursor = conn.cursor()
    
    print("Dropping existing indexes...")
    try:
        cursor.execute("DROP INDEX IF EXISTS ix_users_email")
        cursor.execute("DROP INDEX IF EXISTS ix_users_role_email")
    except Exception as e:
        print(f"Index drop error: {e}")
        
    print("Recreating schema via SQLAlchemy...")
    import sys
    sys.path.insert(0, ".")
    from core.database import engine
    from models import Base
    
    Base.metadata.create_all(bind=engine)
    print("New users table created.")
    
    print("Migrating data...")
    # Fetch old users
    cursor.execute("SELECT * FROM users_old")
    old_users = cursor.fetchall()
    
    for u in old_users:
        cursor.execute("PRAGMA table_info(users_old)")
        cols = [col[1] for col in cursor.fetchall()]
        
        placeholders = ",".join(["?"] * len(cols))
        col_names = ",".join(cols)
        
        row_data = list(u)
        row_data[0] = str(row_data[0])
        
        try:
            cursor.execute(f"INSERT INTO users ({col_names}) VALUES ({placeholders})", row_data)
        except Exception as e:
            print(f"Error inserting user {row_data[0]}: {e}")
            
    print("Dropping old users table...")
    cursor.execute("DROP TABLE users_old")
    
    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate_users()
