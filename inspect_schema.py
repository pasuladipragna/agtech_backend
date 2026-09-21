import sqlite3

def check_schema():
    conn = sqlite3.connect("smart_agritech.db")
    cursor = conn.cursor()
    
    for table in ["farmer_profiles", "registration_requests", "farms", "users"]:
        print(f"--- {table} ---")
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            for col in columns:
                print(col)
        except Exception as e:
            print(f"Error: {e}")
            
if __name__ == "__main__":
    check_schema()
