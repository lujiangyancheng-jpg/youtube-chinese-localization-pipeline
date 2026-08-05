@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "localizer_gui.pyw"
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw "localizer_gui.pyw"
    exit /b 0
)

echo Python was not found. Install the project dependencies first.
pause
exit /b 1
