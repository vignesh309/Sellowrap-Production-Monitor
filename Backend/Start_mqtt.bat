@echo off
taskkill /f /im cloudflared.exe >nul 2>&1
cd /d "C:\Users\admin\Desktop\Production Monitor\Backend"
python mqtt_listener.py
pause