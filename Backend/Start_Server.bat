@echo off
:: 1. Navigate to your specific project folder
cd /d "C:\Users\admin\Desktop\Sellowrap Production Monitor Version 2\Backend"

:: 2. Start the MQTT Listener in a brand new, parallel black window
start "MQTT IoT Listener" cmd /k python mqtt_listener.py

:: 3. Start the FastAPI Web Server in this original window
python main.py

pause