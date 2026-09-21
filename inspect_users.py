import sqlite3

def check_users():
    conn = sqlite3.connect("smart_agritech.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    for u in users:
        print(u)
        
if __name__ == "__main__":
    check_users()
