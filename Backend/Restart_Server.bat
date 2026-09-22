@echo off
echo Restarting Production Monitor...

:: 1. Navigate to current directory
cd /d "%~dp0"

:: 2. Kill existing background processes
echo Stopping current services...
wmic process where "name='python.exe' and commandline like '%%main.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%mqtt_listener.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%moulding_machines_data_monitor.py%%'" call terminate >nul 2>&1

:: 3. Wait 3 seconds to let Windows release the network ports
echo Waiting for ports to close...
timeout /t 3 /nobreak >nul

:: 4. Trigger your existing Start_Server.bat file
echo Booting up Production Monitor services...
start "" "Start_Server.bat"

echo.
echo Restart command issued successfully! You can close this window.
pause