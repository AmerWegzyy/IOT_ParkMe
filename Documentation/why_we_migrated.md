# ParkMe — Why We Migrated to Google Cloud + Firebase

A quick explanation for the team on what changed, why, and what you need to know.

---

## Why Did We Migrate?

### 1. Instructor Requirement
Our instructor asked us to use **Google Cloud** and **Google Firebase** for the project infrastructure.

### 2. Free Credits
Technion provides Google Cloud coupons — so the entire infrastructure is **free** for us. With Render + Supabase, we would hit free tier limits quickly.

### 3. Better Fit for IoT
- **Google Cloud Run** scales to zero — we don't pay when nobody is using the system (and it wakes up automatically when an ESP32 sends data)
- **Firebase Firestore** has built-in real-time capabilities, which fits perfectly with our live parking updates
- **Firebase has excellent web SDKs** — easier integration with our web app if needed

### 4. Everything Under One Roof
Before, we had two separate services (Render for server, Supabase for database). Now **both the server and database are managed by Google** — one dashboard, one billing, one set of credentials.

---

## What Changed?

### The Server (where our code runs)

| | Before | After |
|---|---|---|
| **Platform** | Render | Google Cloud Run |
| **What it runs** | Same FastAPI + Uvicorn | Same FastAPI + Uvicorn |
| **Region** | Frankfurt, Germany | Tel Aviv, Israel (`me-west1`) — **closer to Technion!** |
| **Deployment** | Push to GitHub → Render auto-deploys | `gcloud builds submit` → Cloud Build auto-deploys |

> **For you as a developer:** The server code (FastAPI, endpoints, logic) works exactly the same. The difference is just *where* it runs.

---

### The Database (where our data is stored)

| | Before (SQL) | After (Firestore) |
|---|---|---|
| **Type** | PostgreSQL (relational) | Firestore (NoSQL / document-based) |
| **Structure** | Tables with rows & columns | Collections with JSON documents |
| **Queries** | SQL (`SELECT * FROM users WHERE...`) | Firestore SDK (`db.collection("users").where(...)`) |
| **JOINs** | Built-in (`JOIN users ON...`) | Done manually in Python (two queries + merge) |
| **Local file** | `parkme.db` (SQLite for dev) | No local file — always connects to cloud |

> **For you as a developer:** If you write new endpoints or modify existing ones, you'll use Firestore SDK calls instead of SQL. See examples below.

---

## What Does the Code Look Like Now?

### Reading data — Before vs After

**Before (SQL):**
```python
# Find a user by email
user = db.execute(
    text("SELECT id, name, email, role FROM users WHERE email = :email"),
    {"email": "student@technion.ac.il"}
).fetchone()

print(user.name)  # "John Doe"
```

**After (Firestore):**
```python
# Find a user by email
users_query = db.collection("users") \
    .where("email", "==", "student@technion.ac.il") \
    .limit(1).get()

user = users_query[0].to_dict()
print(user["name"])  # "John Doe"
```

---

### Writing data — Before vs After

**Before (SQL):**
```python
db.execute(
    text("INSERT INTO parking_logs (spot_id, license_plate) VALUES (:spot, :plate)"),
    {"spot": "A1", "plate": "1234567"}
)
db.commit()
```

**After (Firestore):**
```python
db.collection("parking_logs").add({
    "spot_id": "A1",
    "license_plate": "1234567"
})
# No commit needed — Firestore writes are instant
```

---

### Updating data — Before vs After

**Before (SQL):**
```python
db.execute(
    text("UPDATE parking_spots SET is_occupied = TRUE WHERE id = :id"),
    {"id": "A1"}
)
db.commit()
```

**After (Firestore):**
```python
db.collection("parking_spots").document("A1").update({
    "is_occupied": True
})
```

---

## What Stays Exactly the Same?

All of these are **unchanged** — no need to touch them:

- ✅ All API endpoint URLs (`/api/v1/spots`, `/api/v1/sensors/heartbeat`, etc.)
- ✅ All request and response JSON formats
- ✅ The Web Frontend (HTML/CSS/JS — zero changes)
- ✅ ESP32 sensor code (just update the server URL)
- ✅ JWT authentication for users
- ✅ License plate OCR processing
- ✅ Real-time SSE updates

---

## What Do I Need to Do as a Team Member?

### If you work on the Backend:

1. **Get the `serviceAccountKey.json`** file from the team lead (or generate your own from Firebase Console)
2. **Place it in `Backend/`**
3. **Set the env variable:** `export GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json`
4. **Run as usual:** `uvicorn main:app --reload`
5. When writing new database queries, use **Firestore SDK** instead of SQL (see examples above)

### If you work on the ESP32 / Hardware:

Nothing changes. Just update the server URL in the ESP32 code once deployed.

### If you work on the Web Frontend:

Nothing changes. The frontend is served by the same FastAPI backend.

---

## Key Files Changed

| File | What |
|------|------|
| `Backend/main.py` | All SQL queries → Firestore SDK calls |
| `Backend/requirements.txt` | Removed `sqlalchemy`, added `firebase-admin` |
| `Backend/Dockerfile` | Removed PostgreSQL libs, reads `$PORT` from Cloud Run |
| `Backend/cloudbuild.yaml` | **New** — CI/CD pipeline for Google Cloud (replaces `render.yaml`) |
| `Backend/seed_firestore.py` | **New** — Seeds Firestore with test data |
| `Backend/.env.example` | Updated env vars for Firebase |

---

## Questions?

Check the `Documentation/` folder for more details:
- `setup_guide.md` — How to set up everything from scratch
- `how_to_run_locally.md` — How to run locally for development
- `firestore_database_structure.md` — How the data is organized in Firestore
- `migration_to_google_cloud_and_firebase.md` — Full technical diff of what changed
