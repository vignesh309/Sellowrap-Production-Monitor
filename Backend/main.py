import uvicorn
import os
import sys
import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from logging.handlers import TimedRotatingFileHandler

# 🚨 Import our relocated functions!
from services.telegram_notifier import start_scheduler
from summary_worker import start_summary_worker
from apscheduler.schedulers.background import BackgroundScheduler
from services.automated_email import send_morning_digest

# Import our routers
from routers import frontend, master, reports, auth, production_entry, production_entry_stage_1, fetchdata, erp_integration, email_notifier

# =========================
# Logging Configuration
# =========================
# 1. Create a Handler that rotates the log every 4 hours
# backupCount=1 means it keeps the current 4-hour file and ONE previous 4-hour file. 
# Anything older than 8 hours is automatically deleted!
log_handler = TimedRotatingFileHandler(
    "fastapi_logs.txt", 
    when="H",          # H = Hours
    interval=4,        # Every 4 hours
    backupCount=1,     # Keep only 1 backup file
    encoding="utf-8"   # This also permanently fixes your Emoji crash bug!
)

# 2. Configure the root logger
logging.basicConfig(
    handlers=[log_handler],
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 3. Intercept all normal print() statements and route them to the logger
class StreamToLogger:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, message):
        if message.rstrip() != "":
            self.logger.log(self.level, message.rstrip())

    def flush(self):
        pass

    # 🚨 ADD THIS MISSING METHOD
    def isatty(self):
        return False

# Force sys.stdout (prints) and sys.stderr (errors) into our rotator
sys.stdout = StreamToLogger(logging.getLogger(), logging.INFO)
# 🚨 COMMENT OUT OR DELETE THIS LINE:
# Do NOT redirect sys.stderr! This permanently prevents the infinite Windows crash loop.
# sys.stderr = StreamToLogger(logging.getLogger(), logging.ERROR)

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

    # Start the automated email scheduler once with the application lifecycle.
    scheduler.start()

    yield  # The FastAPI server runs while yielding here

    scheduler.shutdown(wait=False)

# Initialize the automated background scheduler
scheduler = BackgroundScheduler()

# 🚨 CHANGE THE TIME HERE

scheduler.add_job(send_morning_digest, 'cron', hour=11, minute=15)  # Adjust the time as needed

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
app.include_router(production_entry_stage_1.router)
app.include_router(fetchdata.router)
app.include_router(erp_integration.router)  # 🚨 NEW: ERP Integration Router
app.include_router(email_notifier.router)  # 🚨 NEW: Email Notifier Router
# =========================
# Main Entry
# =========================
if __name__ == "__main__":
    # Reload mode is for development only; it can duplicate background workers in production.
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)