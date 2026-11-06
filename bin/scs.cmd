@echo off
rem ============================================================================
rem Agent Continuity Steward (SCS_AG_v2) — Windows Command Wrapper (scs.cmd)
rem Zero external dependencies. Discovers active Python virtualenv or system Python.
rem ============================================================================
setlocal enabledelayedexpansion

rem 1. Check if VIRTUAL_ENV is active in the current session
if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\scs.exe" (
        "%VIRTUAL_ENV%\Scripts\scs.exe" %*
        exit /b %ERRORLEVEL%
    )
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
        "%VIRTUAL_ENV%\Scripts\python.exe" -m engine.scs_cli %*
        exit /b %ERRORLEVEL%
    )
)

rem 2. Check local workspace .venv in current directory
if exist "%CD%\.venv\Scripts\scs.exe" (
    "%CD%\.venv\Scripts\scs.exe" %*
    exit /b %ERRORLEVEL%
)
if exist "%CD%\.venv\Scripts\python.exe" (
    "%CD%\.venv\Scripts\python.exe" -m engine.scs_cli %*
    exit /b %ERRORLEVEL%
)

rem 3. Check repository root .venv relative to this script
set "REPO_ROOT=%~dp0.."
if exist "%REPO_ROOT%\.venv\Scripts\scs.exe" (
    "%REPO_ROOT%\.venv\Scripts\scs.exe" %*
    exit /b %ERRORLEVEL%
)
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m engine.scs_cli %*
    exit /b %ERRORLEVEL%
)

rem 4. Fallback to system Python
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"
    python -m engine.scs_cli %*
    exit /b %ERRORLEVEL%
)

echo [X] Error: Python was not found in your environment or active virtualenv.
echo Please install Python 3.10+ or activate a virtual environment with .venv\Scripts\activate
exit /b 1
