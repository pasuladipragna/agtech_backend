import httpx, time, sys
from datetime import datetime

BASE = "http://localhost:8000/api/v1"
RESULTS = []

def log(status, section, test, detail="", code=None):
    msg = status + " [" + section + "] " + test + (" [" + str(code) + "]" if code else "")
    if detail: msg += "\n       -> " + str(detail)[:100]
    print(msg)
    RESULTS.append({"s": status, "sec": section, "t": test, "d": str(detail)[:120]})

def req(method, url, data=None, token=None, form=False, params=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    full = (BASE + url) if url.startswith("/") else url
    try:
        if method == "GET": return httpx.get(full, headers=h, params=params, timeout=10)
        elif method == "POST":
            if form: return httpx.post(full, data=data, headers=h, timeout=10)
            h["Content-Type"] = "application/json"
            return httpx.post(full, json=data, headers=h, timeout=10)
        elif method == "PUT":
            h["Content-Type"] = "application/json"
            return httpx.put(full, json=data, headers=h, timeout=10)
        elif method == "PATCH":
            h["Content-Type"] = "application/json"
            return httpx.patch(full, json=data, headers=h, timeout=10)
        elif method == "DELETE": return httpx.delete(full, headers=h, timeout=10)
    except Exception as e:
        print("  ERROR:", e)
        return None

TS = str(int(time.time()))
TEST_EMAIL = "testfarmer_" + TS + "@agritech.test"
admin_token = farmer_token = reg_id = farmer_uid = farm_id = field_id = crop_id = None
rover_db_id = rover_hw_id = post_id = ticket_id = None

print("=" * 65)
print("  Smart AgriTech E2E Test Suite")
print("=" * 65)

# 0. HEALTH
print("\n-- 0. Health Check")
r = req("GET", "http://localhost:8000/health")
log("PASS" if r and r.status_code==200 else "FAIL", "Health", "GET /health", getattr(r,"text",""), getattr(r,"status_code",None))
if not r or r.status_code != 200: sys.exit(1)
r = req("GET", "http://localhost:8000/")
log("PASS" if r and r.status_code==200 else "FAIL", "Health", "GET / root", "", getattr(r,"status_code",None))

# 1. AUTH
print("\n-- 1. Authentication")
r = req("POST", "/auth/login", {"email": "admin@agritech.com", "password": "Admin@123456"})
if r and r.status_code == 200:
    d = r.json(); admin_token = d.get("access_token")
    log("PASS", "Auth", "Admin login", "role=" + d["user"]["role"], 200)
else:
    log("FAIL", "Auth", "Admin login", getattr(r,"text",""), getattr(r,"status_code",None))

r = req("POST", "/auth/login", {"email": "admin@agritech.com", "password": "WRONG"})
log("PASS" if r and r.status_code==401 else "FAIL", "Auth", "Wrong password -> 401", "", getattr(r,"status_code",None))

r = req("GET", "/auth/me", token=admin_token)
log("PASS" if r and r.status_code==200 else "FAIL", "Auth", "GET /auth/me admin", "", getattr(r,"status_code",None))

r = req("GET", "/auth/me")
log("PASS" if r and r.status_code==401 else "FAIL", "Auth", "GET /auth/me no token -> 401", "", getattr(r,"status_code",None))

# 2. REGISTRATION
print("\n-- 2. Farmer Registration")
fd = {"full_name": "Test Farmer " + TS, "email": TEST_EMAIL, "phone": "9876543210",
      "farm_name": "Green Valley Farm " + TS, "farm_location": "Punjab India",
      "farm_area_hectares": "15.5", "main_crops": "Wheat Paddy", "preferred_language": "en"}
r = req("POST", "/registration/submit", fd, form=True)
if r and r.status_code == 201:
    reg_id = r.json().get("id")
    log("PASS", "Registration", "POST /registration/submit", "id=" + str(reg_id), 201)
else:
    log("FAIL", "Registration", "POST /registration/submit", getattr(r,"text",""), getattr(r,"status_code",None))

r = req("POST", "/registration/submit", fd, form=True)
log("PASS" if r and r.status_code==409 else "FAIL", "Registration", "Duplicate -> 409", "", getattr(r,"status_code",None))

r = req("GET", "/registration/status", params={"email": TEST_EMAIL})
log("PASS" if r and r.status_code==200 else "FAIL", "Registration", "GET /registration/status", "", getattr(r,"status_code",None))

r = req("GET", "/registration/status", params={"email": "nope@x.com"})
log("PASS" if r and r.status_code==404 else "FAIL", "Registration", "Unknown email -> 404", "", getattr(r,"status_code",None))

# 3. ADMIN REG MANAGEMENT
print("\n-- 3. Admin Registration Management")
r = req("GET", "/admin/registrations", token=admin_token)
log("PASS" if r and r.status_code==200 else "FAIL", "Admin", "GET /admin/registrations", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))

if reg_id:
    r = req("GET", "/admin/registrations/" + reg_id, token=admin_token)
    log("PASS" if r and r.status_code==200 else "FAIL", "Admin", "GET /admin/registrations/:id", "", getattr(r,"status_code",None))

r = req("GET", "/admin/registrations")
log("PASS" if r and r.status_code in (401,403) else "FAIL", "Admin", "No token -> 401", "", getattr(r,"status_code",None))

if reg_id:
    apwd = "Farmer@123_" + TS
    r = req("PATCH", "/admin/registrations/" + reg_id + "/status",
            {"status": "APPROVED", "assigned_password": apwd, "assigned_username": "farmer_" + TS},
            token=admin_token)
    if r and r.status_code == 200:
        farmer_uid = r.json().get("created_user_id")
        log("PASS", "Admin", "Approve registration", "farmer_uid=" + str(farmer_uid), 200)
    else:
        log("FAIL", "Admin", "Approve registration", getattr(r,"text",""), getattr(r,"status_code",None))
    r = req("PATCH", "/admin/registrations/" + reg_id + "/status", {"status": "APPROVED"}, token=admin_token)
    log("PASS" if r and r.status_code==409 else "FAIL", "Admin", "Double-approve -> 409", "", getattr(r,"status_code",None))

# 4. FARMER LOGIN
print("\n-- 4. Farmer Login")
if farmer_uid:
    r = req("POST", "/auth/login", {"email": TEST_EMAIL, "password": "Farmer@123_" + TS})
    if r and r.status_code == 200:
        farmer_token = r.json().get("access_token")
        log("PASS", "Auth", "Farmer login", "role=" + r.json()["user"]["role"], 200)
    else:
        log("FAIL", "Auth", "Farmer login", getattr(r,"text",""), getattr(r,"status_code",None))
    if farmer_token:
        r = req("GET", "/auth/me", token=farmer_token)
        log("PASS" if r and r.status_code==200 else "FAIL", "Auth", "GET /auth/me farmer", "", getattr(r,"status_code",None))

# 5. FARMS
print("\n-- 5. Farms")
r = req("GET", "/farms", token=admin_token)
if r and r.status_code == 200:
    farms = r.json()
    if farms: farm_id = farms[0]["id"]
    log("PASS", "Farms", "GET /farms admin", "count=" + str(len(farms)), 200)
else:
    log("FAIL", "Farms", "GET /farms admin", getattr(r,"text",""), getattr(r,"status_code",None))

if farmer_token:
    r = req("GET", "/farms", token=farmer_token)
    if r and r.status_code == 200:
        ff = r.json()
        if ff and not farm_id: farm_id = ff[0]["id"]
        # Ensure we use the farm owned by this farmer
        farm_id = ff[-1]["id"] if ff else farm_id
        log("PASS", "Farms", "GET /farms farmer", "count=" + str(len(ff)), 200)
    else:
        log("FAIL", "Farms", "GET /farms farmer", getattr(r,"text",""), getattr(r,"status_code",None))

if farm_id:
    r = req("GET", "/farms/" + farm_id, token=admin_token)
    log("PASS" if r and r.status_code==200 else "FAIL", "Farms", "GET /farms/:id", "", getattr(r,"status_code",None))
    r = req("PUT", "/farms/" + farm_id, {"description": "Updated via E2E"}, token=admin_token)
    log("PASS" if r and r.status_code==200 else "FAIL", "Farms", "PUT /farms/:id", "", getattr(r,"status_code",None))

r = req("GET", "/farms/nonexistent-id", token=admin_token)
log("PASS" if r and r.status_code==404 else "FAIL", "Farms", "Invalid farm -> 404", "", getattr(r,"status_code",None))

# 6. FIELDS
print("\n-- 6. Fields")
tok = farmer_token or admin_token
if farm_id and tok:
    r = req("POST", "/fields", {"farm_id": farm_id, "name": "North Field " + TS, "area_hectares": 3.5, "notes": "E2E"}, token=tok)
    if r and r.status_code == 201:
        field_id = r.json().get("id")
        log("PASS", "Fields", "POST /fields", "id=" + str(field_id), 201)
    else:
        log("FAIL", "Fields", "POST /fields", getattr(r,"text",""), getattr(r,"status_code",None))
    r = req("GET", "/fields", token=tok, params={"farm_id": farm_id})
    log("PASS" if r and r.status_code==200 else "FAIL", "Fields", "GET /fields", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))
    if field_id:
        r = req("PUT", "/fields/" + field_id, {"area_hectares": 4.2, "notes": "Updated"}, token=tok)
        log("PASS" if r and r.status_code==200 else "FAIL", "Fields", "PUT /fields/:id", "", getattr(r,"status_code",None))

# 7. CROPS
print("\n-- 7. Crops")
if field_id and tok:
    r = req("POST", "/crops", {"field_id": field_id, "name": "Wheat", "variety": "HD-2967",
                                "growth_stage": "Tillering", "planting_date": "2026-01-15",
                                "status": "Monitoring", "notes": "E2E"}, token=tok)
    if r and r.status_code == 201:
        crop_id = r.json().get("id")
        log("PASS", "Crops", "POST /crops", "id=" + str(crop_id), 201)
    else:
        log("FAIL", "Crops", "POST /crops", getattr(r,"text",""), getattr(r,"status_code",None))
    r = req("GET", "/crops", token=tok, params={"field_id": field_id})
    log("PASS" if r and r.status_code==200 else "FAIL", "Crops", "GET /crops", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))
    if crop_id:
        r = req("PUT", "/crops/" + crop_id, {"growth_stage": "Heading", "status": "Healthy"}, token=tok)
        log("PASS" if r and r.status_code==200 else "FAIL", "Crops", "PUT /crops/:id", "", getattr(r,"status_code",None))

# 8. ROVERS
print("\n-- 8. Rovers")
r = req("GET", "/rovers", token=admin_token)
if r and r.status_code == 200:
    rovs = r.json()
    if rovs: rover_hw_id = rovs[0].get("rover_id"); rover_db_id = rovs[0].get("id")
    log("PASS", "Rovers", "GET /rovers admin", "count=" + str(len(rovs)), 200)
else:
    log("FAIL", "Rovers", "GET /rovers", getattr(r,"text",""), getattr(r,"status_code",None))

nrid = "ROVER-E2E-" + TS
r = req("POST", "/admin/rovers", {"rover_id": nrid, "name": "E2E Rover " + TS, "description": "E2E"}, token=admin_token)
if r and r.status_code == 201:
    rover_db_id = r.json().get("id"); rover_hw_id = nrid
    log("PASS", "Rovers", "POST /rovers", "id=" + str(rover_db_id), 201)
else:
    log("FAIL", "Rovers", "POST /rovers", getattr(r,"text",""), getattr(r,"status_code",None))

if rover_hw_id:
    r = req("GET", "/rovers/" + rover_hw_id, token=admin_token)
    log("PASS" if r and r.status_code==200 else "FAIL", "Rovers", "GET /rovers/:rover_id", "", getattr(r,"status_code",None))

if rover_db_id and farm_id:
    r = req("POST", "/admin/rovers/" + rover_db_id + "/assign", {"farm_id": farm_id}, token=admin_token)
    log("PASS" if r and r.status_code in (200,201) else "WARN", "Rovers", "POST /rovers/assignments", getattr(r,"text",""), getattr(r,"status_code",None))

if rover_hw_id:
    r = req("POST", "/rovers/" + rover_hw_id + "/command", {"command": "EMERGENCY_STOP", "params": {}}, token=admin_token)
    log("PASS" if r and r.status_code in (200,201) else "WARN", "Rovers", "POST rover command EMERGENCY_STOP", getattr(r,"text",""), getattr(r,"status_code",None))

# 9. ADMIN FARMER MANAGEMENT
print("\n-- 9. Admin Farmer Management")
r = req("GET", "/admin/farmers", token=admin_token)
log("PASS" if r and r.status_code==200 else "FAIL", "Admin", "GET /admin/farmers", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))
if farmer_uid:
    r = req("PATCH", "/admin/farmers/" + farmer_uid + "/activate", {"is_active": True}, token=admin_token)
    log("PASS" if r and r.status_code==200 else "FAIL", "Admin", "PATCH farmer activate", "", getattr(r,"status_code",None))

# 10. PRODUCTS
print("\n-- 10. Products")
r = req("GET", "/products", token=admin_token)
log("PASS" if r and r.status_code==200 else "FAIL", "Products", "GET /products", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))
r = req("POST", "/admin/products", {"name": "E2E Pesticide " + TS, "product_type": "Pesticide", "target_crop": "Wheat"}, token=admin_token)
log("PASS" if r and r.status_code==201 else "FAIL", "Products", "POST /products", getattr(r,"text",""), getattr(r,"status_code",None))
if farmer_token:
    r = req("POST", "/products", {"name": "Hack", "product_type": "Pesticide"}, token=farmer_token)
    log("PASS" if r and r.status_code in (401,403) else "WARN", "Products", "Farmer POST product -> 403", "", getattr(r,"status_code",None))

# 11. NOTIFICATIONS
print("\n-- 11. Notifications")
if farmer_token:
    r = req("GET", "/notifications", token=farmer_token)
    notifs = r.json() if r and r.status_code==200 else []
    log("PASS" if r and r.status_code==200 else "FAIL", "Notifications", "GET /notifications", "count=" + str(len(notifs)), getattr(r,"status_code",None))
    if notifs:
        nid = notifs[0].get("id")
        r2 = req("PATCH", "/notifications/" + nid + "/read", {}, token=farmer_token)
        log("PASS" if r2 and r2.status_code in (200,204) else "WARN", "Notifications", "PATCH notification read", "", getattr(r2,"status_code",None))

# 12. COMMUNITY
print("\n-- 12. Community")
tok = farmer_token or admin_token
r = req("GET", "/community/posts", token=tok)
log("PASS" if r and r.status_code==200 else "FAIL", "Community", "GET /community/posts", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))
r = req("POST", "/community/posts", {"title": "E2E Post " + TS, "content": "E2E test community post", "tags": "test"}, token=tok)
if r and r.status_code in (200,201):
    post_id = r.json().get("id")
    log("PASS", "Community", "POST /community/posts", "id=" + str(post_id), r.status_code)
else:
    log("FAIL", "Community", "POST /community/posts", getattr(r,"text",""), getattr(r,"status_code",None))
if post_id:
    r = req("POST", "/community/posts/" + post_id + "/comments", {"content": "E2E test comment"}, token=tok)
    log("PASS" if r and r.status_code in (200,201) else "FAIL", "Community", "POST /community/posts/:id/comments", getattr(r,"text",""), getattr(r,"status_code",None))

# 13. SUPPORT TICKETS
print("\n-- 13. Support Tickets")
tok = farmer_token or admin_token
r = req("POST", "/support/tickets", {"subject": "E2E Ticket " + TS, "category": "Technical Issue", "description": "E2E test ticket", "priority": "Medium"}, token=tok)
if r and r.status_code in (200,201):
    ticket_id = r.json().get("id")
    log("PASS", "Support", "POST /support/tickets", "id=" + str(ticket_id), r.status_code)
else:
    log("FAIL", "Support", "POST /support/tickets", getattr(r,"text",""), getattr(r,"status_code",None))
r = req("GET", "/support/tickets", token=tok)
log("PASS" if r and r.status_code==200 else "FAIL", "Support", "GET /support/tickets", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))
if ticket_id:
    r = req("POST", "/support/tickets/" + ticket_id + "/messages", {"message": "E2E reply"}, token=tok)
    log("PASS" if r and r.status_code in (200,201) else "WARN", "Support", "POST ticket message", getattr(r,"text",""), getattr(r,"status_code",None))
    if admin_token:
        r = req("PATCH", "/support/tickets/" + ticket_id + "/status", {"status": "IN_PROGRESS"}, token=admin_token)
        log("PASS" if r and r.status_code==200 else "WARN", "Support", "Admin PATCH ticket status", "", getattr(r,"status_code",None))

# 14. DASHBOARD
print("\n-- 14. Farmer Dashboard")
if farmer_token:
    r = req("GET", "/farmer/dashboard/summary", token=farmer_token)
    if r and r.status_code == 200:
        d = r.json()
        log("PASS", "Dashboard", "GET /farmer/dashboard/summary", "farm=" + str(d.get("farm_name")) + " fields=" + str(d.get("total_fields")), 200)
    else:
        log("FAIL", "Dashboard", "GET /farmer/dashboard/summary", getattr(r,"text",""), getattr(r,"status_code",None))

# 15. REPORTS
print("\n-- 15. Reports")
r = req("GET", "/reports", token=admin_token)
log("PASS" if r and r.status_code==200 else "WARN", "Reports", "GET /reports admin", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))

# 16. SPRAY
print("\n-- 16. Spray Sessions")
r = req("GET", "/spray-sessions", token=admin_token)
log("PASS" if r and r.status_code==200 else "WARN", "Spray", "GET /spray-sessions", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))

# 17. ACTIVITY LOGS
print("\n-- 17. Activity Logs")
r = req("GET", "/admin/activity-logs", token=admin_token)
log("PASS" if r and r.status_code==200 else "WARN", "Admin", "GET /admin/activity-logs", "count=" + str(len(r.json()) if r and r.status_code==200 else "?"), getattr(r,"status_code",None))

# 18. DOCS
print("\n-- 18. API Docs")
r = req("GET", "http://localhost:8000/docs")
log("PASS" if r and r.status_code==200 else "WARN", "Docs", "GET /docs Swagger UI", "", getattr(r,"status_code",None))
r = req("GET", "http://localhost:8000/openapi.json")
if r and r.status_code==200:
    log("PASS", "Docs", "GET /openapi.json", "total_routes=" + str(len(r.json().get("paths", {}))), 200)
else:
    log("WARN", "Docs", "GET /openapi.json", "", getattr(r,"status_code",None))

# 19. CROP DETECTION
print("\n-- 19. Crop Detection")
if field_id:
    # Test Analyze Image
    img_path = "test_e2e_leaf.jpg"
    with open(img_path, "wb") as f:
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03\x03\x03\x04\x06\x04\x04\x04\x04\x04\x08\x06\x06\x05\x06\t\x08\n\n\t\x08\t\t\n\x0c\x0f\x0c\n\x0b\x0e\x0b\t\t\r\x11\r\x0e\x0f\x10\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x00\xff\xd9')
    
    data = {"field_id": field_id}
    if crop_id:
        data["crop_id"] = crop_id
    
    import httpx, os
    with httpx.Client() as client:
        with open(img_path, "rb") as f:
            r = client.post(
                f"{BASE}/crop-health/analyze-image", 
                headers={"Authorization": f"Bearer {admin_token}"},
                data=data,
                files={"file": ("test_e2e_leaf.jpg", f, "image/jpeg")}
            )
        log("PASS" if r.status_code==200 else "FAIL", "Detection", "POST /crop-health/analyze-image", f"type={r.json().get('detection_type')} available={r.json().get('analysis_available')}" if r.status_code==200 else "", getattr(r,"status_code",None))
        
        # Test Analyze Video
        vid_path = "test_e2e_video.mp4"
        with open(vid_path, "wb") as f:
            f.write(b'\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41\x00\x00\x00\x08free')
        with open(vid_path, "rb") as f:
            r_vid = client.post(
                f"{BASE}/crop-health/analyze-video", 
                headers={"Authorization": f"Bearer {admin_token}"},
                data=data,
                files={"file": ("test_e2e_video.mp4", f, "video/mp4")}
            )
        log("PASS" if r_vid.status_code==200 else "FAIL", "Detection", "POST /crop-health/analyze-video", f"job_id={r_vid.json().get('job_id')}" if r_vid.status_code==200 else "", getattr(r_vid,"status_code",None))
        
        os.remove(img_path)
        os.remove(vid_path)

# 20. CLEANUP
print("\n-- 20. Cleanup")
if field_id:
    tok = farmer_token or admin_token
    r = req("DELETE", "/fields/" + field_id, token=tok)
    log("PASS" if r and r.status_code in (200,204) else "WARN", "Cleanup", "DELETE /fields/:id", "", getattr(r,"status_code",None))

total = len(RESULTS)
passed = sum(1 for x in RESULTS if x["s"] == "PASS")
failed = sum(1 for x in RESULTS if x["s"] == "FAIL")
warned = sum(1 for x in RESULTS if x["s"] == "WARN")
print()
print("=" * 65)
print("  SUMMARY")
print("  PASSED: " + str(passed) + "/" + str(total))
print("  FAILED: " + str(failed) + "/" + str(total))
print("  WARNED: " + str(warned) + "/" + str(total))
print("  Pass Rate: " + str(round(passed/total*100,1) if total else 0) + "%")
if failed > 0:
    print("\n  -- FAILURES --")
    for x in RESULTS:
        if x["s"] == "FAIL":
            print("  FAIL [" + x["sec"] + "] " + x["t"])
            if x["d"]: print("       -> " + x["d"])
if warned > 0:
    print("\n  -- WARNINGS --")
    for x in RESULTS:
        if x["s"] == "WARN":
            print("  WARN [" + x["sec"] + "] " + x["t"])
            if x["d"]: print("       -> " + x["d"])
print("=" * 65)
