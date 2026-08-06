import uvicorn
import os
import sys
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 🚨 APScheduler Imports
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# 🚨 Import our relocated functions!
from services.telegram_notifier import start_scheduler
from summary_worker import start_summary_worker

# 🚨 Import the new Auto-Finalization worker!
from Backend.services.auto_worker import run_auto_finalization

# Import our routers
from routers import frontend, master, reports, auth, production_entry, fetchdata

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

    # 3. Start APScheduler for Auto-Finalization
    scheduler = BackgroundScheduler()
    
    # 07:05 AM -> Finalize Shift A from yesterday
    scheduler.add_job(
        run_auto_finalization, 
        CronTrigger(hour=7, minute=5), 
        args=['A'], 
        id="auto_finalize_shift_A", 
        replace_existing=True
    )
    
    # 19:05 PM -> Finalize Shift B from yesterday/today
    scheduler.add_job(
        run_auto_finalization, 
        CronTrigger(hour=19, minute=5), 
        args=['B'], 
        id="auto_finalize_shift_B", 
        replace_existing=True
    )
    
    scheduler.start()
    print("Background Task Scheduler Started successfully.")

    yield  # The FastAPI server runs while yielding here

    # 4. Clean Shutdown
    scheduler.shutdown()
    print("Background Task Scheduler Stopped cleanly.")

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

# =========================
# Main Entry
# =========================
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)