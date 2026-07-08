@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SOR Public Archiver

echo Starting SOR Public Archiver...
echo Folder: %CD%
echo.

REM Prefer the Windows Python launcher (same as double-click on .py)
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  if exist "%ProgramFiles%\Python311\python.exe" set "PY=%ProgramFiles%\Python311\python.exe"
)
if not defined PY (
  echo ERROR: No Python found.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  echo Check "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Using: %PY%
%PY% -c "import sys; print(sys.executable); print(sys.version)"
echo.

echo Checking / installing dependencies for this Python...
%PY% -m pip install --user -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo pip install failed — trying without --user...
  %PY% -m pip install -r "%~dp0requirements.txt"
)
echo.

%PY% "%~dp0gui.py"
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo GUI exited with code %ERR%.
  if exist "%~dp0gui_error.log" (
    echo --- gui_error.log ---
    type "%~dp0gui_error.log"
  )
  pause
  exit /b %ERR%
)
endlocal
