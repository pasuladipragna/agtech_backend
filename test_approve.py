import httpx
import time

API_URL = "http://127.0.0.1:8000/api/v1"

def test_approve():
    client = httpx.Client()
    # 1. Login as admin
    login_data = {"email": "admin@agritech.com", "password": "adminpassword"} # default admin
    res = client.post(f"{API_URL}/auth/login", json=login_data)
    if res.status_code != 200:
        print("Admin login failed:", res.text)
        return
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Get registrations
    res = client.get(f"{API_URL}/admin/registrations", headers=headers)
    if res.status_code != 200:
        print("Failed to get registrations:", res.text)
        return
    regs = res.json()
    pending = [r for r in regs if r["status"] == "PENDING" or r["status"] == "UNDER_REVIEW"]
    if not pending:
        print("No pending registrations found.")
        return
    
    reg_id = pending[0]["id"]
    print(f"Approving registration {reg_id}...")
    
    # 3. Approve
    res = client.patch(f"{API_URL}/admin/registrations/{reg_id}/status", json={"status": "APPROVED"}, headers=headers)
    print("Approve response status:", res.status_code)
    print("Approve response body:", res.text)

if __name__ == "__main__":
    test_approve()
