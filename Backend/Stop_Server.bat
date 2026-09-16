@echo off
echo Stopping Sellowrap Production Monitor services...

:: 1. Navigate to current directory
cd /d "%~dp0"

:: 2. Hunt down and terminate specific background Python scripts
wmic process where "name='python.exe' and commandline like '%%main.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%mqtt_listener.py%%'" call terminate >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%moulding_machines_data_monitor.py%%'" call terminate >nul 2>&1

echo.
echo All Sellowrap background services have been successfully stopped!
pause