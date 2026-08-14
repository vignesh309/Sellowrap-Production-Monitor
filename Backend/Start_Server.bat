@echo off
:: 1. Automatically navigate to the folder where this .bat file is located
cd /d "%~dp0"

:: 2. Check if the local IP address is exactly 200.200.210.249 (Production Server)
ipconfig | find "200.200.210.249" >nul

if %errorlevel% == 0 (
    echo Detected Production Server IP 200.200.210.249. Starting background services...
    
    :: 3. Start the MQTT Listener in a brand new, parallel black window
    start "MQTT IoT Listener" cmd /k python services/mqtt_listener.py

    :: 4. Start the Moulding Data Monitor in another brand new, parallel black window
    start "Moulding Monitor" cmd /k python services/moulding_machines_data_monitor.py
) else (
    echo Non-production IP detected. Skipping MQTT Listener and Moulding Monitor...
)

:: 5. Start the FastAPI Web Server in this original window
echo Starting FastAPI Web Server...
python main.py

pause