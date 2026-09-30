@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto broken
".venv\Scripts\python.exe" -c "import pypdf, pypdfium2, requests" >nul 2>nul
if errorlevel 1 goto dependencies
".venv\Scripts\python.exe" -u workflow.py
if errorlevel 1 goto failed
exit /b 0
:missing
echo Run Setup.cmd once before starting a review.
goto help
:broken
echo The toolkit's Python environment is broken or older than Python 3.10.
echo Run Setup.cmd with Python 3.10 or newer to repair it.
goto help
:dependencies
echo Some toolkit dependencies are missing. Run Setup.cmd to install them.
goto help
:failed
echo The review could not start. Read the error above.
:help
echo See START_HERE.md for setup instructions.
pause
exit /b 1
