import uvicorn
import os
import sys
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 🚨 Import our relocated functions!
from services.telegram_notifier import start_scheduler
from summary_worker import start_summary_worker

# Import our routers
from routers import frontend, master, reports, auth, production_entry, fetchdata, erp_integration

# =========================
# Lifespan Events (Startup & Shutdown)
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Start the 4-Hour Telegram Alert Scheduler (Imported from services)
    start_scheduler()
    
    # 2. Start Summary Worker
    worker_thread = threading.Thread(target=start_summary_worker)
    worker_thread.daemon = True  # Ensures it shuts down when the server closes
    worker_thread.start()

    yield  # The FastAPI server runs while yielding here

# =========================
# App Initialization
# =========================
app = FastAPI(lifespan=lifespan)
    
# =========================
# CORS Config
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Directory Setup
# =========================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

if not os.path.exists(FRONTEND_DIR):
    os.makedirs(FRONTEND_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# =========================
# Include Routers
# =========================
app.include_router(frontend.router)
app.include_router(master.router)
app.include_router(reports.router)
app.include_router(auth.router) 
app.include_router(production_entry.router)
app.include_router(fetchdata.router)
app.include_router(erp_integration.router)  # 🚨 NEW: ERP Integration Router

# =========================
# Main Entry
# =========================
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)