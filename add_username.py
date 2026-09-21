import sqlite3

def add_username():
    conn = sqlite3.connect("smart_agritech.db")
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN username VARCHAR(100)")
        print("username column added to users table.")
    except Exception as e:
        print(f"Error (maybe already exists?): {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    add_username()
