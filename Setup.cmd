@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 goto localpython
)
where py >nul 2>nul
if errorlevel 1 goto systempython
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto systempython
py -3 bootstrap_env.py
goto done
:systempython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto missing
python bootstrap_env.py
goto done
:localpython
".venv\Scripts\python.exe" bootstrap_env.py
:done
if errorlevel 1 goto failed
echo Run Start review.cmd to open the browser setup.
pause
exit /b 0
:missing
echo Python 3.10 or newer is required. Python 3.9 and broken environments cannot run this toolkit.
echo Install a current Python version from https://www.python.org/downloads/ and run Setup.cmd again.
pause
exit /b 1
:failed
echo Setup failed. Read the error above, then run Setup.cmd again after fixing it.
pause
exit /b 1
