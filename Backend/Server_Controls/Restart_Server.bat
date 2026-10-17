@echo off
echo Restarting Production Monitor...

:: 1. Navigate to the parent directory (Backend)
cd /d "%~dp0.."

:: 2. Kill existing background processes
echo Stopping current services...
wmic process where "name='python.exe' and commandline like '%%main.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%mqtt_listener.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%moulding_machines_data_monitor.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%energy_meter_data_monitor.py%%'" call terminate >nul 2>&1

:: 3. Wait 3 seconds to let Windows release the network ports
echo Waiting for ports to close...
timeout /t 3 /nobreak >nul

:: 4. Start the background services directly
echo Booting up Production Monitor background services...
start "MQTT IoT Listener" cmd /c "python services/mqtt_listener.py"
start "Moulding Monitor" cmd /c "python services/moulding_machines_data_monitor.py"
start "Energy Meter Monitor" cmd /c "python services/energy_meter_data_monitor.py"

:: 5. Start the FastAPI Web Server
echo Starting FastAPI Web Server...
set PYTHONIOENCODING=utf-8
python main.py