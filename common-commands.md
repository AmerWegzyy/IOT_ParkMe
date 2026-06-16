# ParkMe — Common Terminal Commands

This file contains a quick reference for the most frequent terminal commands used during development.

## 🚀 Running on Localhost

FastAPI is configured to serve the frontend static files directly. Therefore, running the backend server will automatically serve the frontend as well on the same port! You only need one terminal.

### 1. Activate the Virtual Environment
Navigate to the `Backend` directory and activate the virtual environment where your dependencies are installed:
```bash
cd Backend
source venv/bin/activate  # or: source venv2/bin/activate
```

### 2. Run the FastAPI + Frontend Server (Uvicorn)
Start the Uvicorn ASGI server with hot-reloading:
```bash
uvicorn main:app --reload
```
* **Web Frontend** will be served directly at: `http://127.0.0.1:8000/` (just open this in your browser)
* **Backend API** will be running at: `http://127.0.0.1:8000` (API docs at `http://127.0.0.1:8000/docs`)

---

### (Alternative) Running Frontend Separately
If you ever want to run the frontend in isolation on a different port (e.g., port 3000) using Python's built-in HTTP server:
```bash
cd Frontend
python3 -m http.server 3000
```
*The standalone frontend will start at `http://localhost:3000`.*

