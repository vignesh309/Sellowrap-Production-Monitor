from datetime import datetime
from fastapi import HTTPException
import os
import subprocess
import time
import re
import requests
from config import BOT_TOKEN, CHAT_ID

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED_PATH = os.path.join(BASE_DIR, "cloudflared.exe")
TUNNEL_LOG = os.path.join(BASE_DIR, "cf_log.txt")

# =========================
# SECURITY CONFIG
# =========================
EXPIRATION_DATE = datetime(2027, 7, 25)

def check_license():
    """Stops the request if the trial is expired."""
    if datetime.now() > EXPIRATION_DATE:
        raise HTTPException(
            status_code=403, 
            detail="TRIAL EXPIRED. Please contact administrator to renew."
        )

def start_cloudflare_tunnel():
    """Starts the Cloudflare tunnel and sends the URL to Telegram."""
    if os.name == 'nt':
        os.system("taskkill /F /IM cloudflared.exe >nul 2>&1")

    with open(TUNNEL_LOG, "w") as f:
        f.write("")

    if not os.path.exists(CLOUDFLARED_PATH):
        print(f"Error: Could not find cloudflared at {CLOUDFLARED_PATH}")
        return

    print("Starting Cloudflare Tunnel...")
    
    cmd = [CLOUDFLARED_PATH, "tunnel", "--url", "http://localhost:8001", "--logfile", TUNNEL_LOG]
    subprocess.Popen(cmd)

    url = None
    attempts = 0
    while not url and attempts < 30:
        time.sleep(2)
        attempts += 1
        try:
            if os.path.exists(TUNNEL_LOG):
                with open(TUNNEL_LOG, "r", encoding="utf-8") as f:
                    match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", f.read())
                    if match:
                        url = match.group(0)
        except Exception as e:
            pass

    if url:
        message = f"🚀 Sellowrap Production Server is ONLINE\nURL: {url}"
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHAT_ID, "text": message}, timeout=10)
            print(f"Server Tunnel Started Successfully here: {url}")
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
    else:
        print("Failed to capture Cloudflare URL.")