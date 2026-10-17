@echo off
echo Starting Production Monitor services...

:: 1. Navigate to the parent directory (Backend) so Python has the correct working path
cd /d "%~dp0.."

:: 2. Start the background services directly
echo Starting background services...
start "MQTT IoT Listener" cmd /c "python services/mqtt_listener.py"
start "Moulding Monitor" cmd /c "python services/moulding_machines_data_monitor.py"
start "Energy Meter Monitor" cmd /c "python services/energy_meter_data_monitor.py"

:: 3. Start the FastAPI Web Server
echo Starting FastAPI Web Server...
set PYTHONIOENCODING=utf-8
python main.py