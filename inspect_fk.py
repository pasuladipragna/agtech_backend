import sqlite3

def check_fk():
    conn = sqlite3.connect("smart_agritech.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM farmer_profiles")
    print("farmer_profiles:", cursor.fetchall())
    
    cursor.execute("SELECT * FROM registration_requests")
    print("registration_requests:", cursor.fetchall())
        
if __name__ == "__main__":
    check_fk()
