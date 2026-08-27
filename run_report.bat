@echo off
setlocal

rem One-time PDF setup:
rem   py -3 -m pip install -e ".[pdf]"
rem   py -3 -m playwright install chromium

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
if errorlevel 1 (
    echo Could not enter the project directory: "%SCRIPT_DIR%" 1>&2
    exit /b 1
)

set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
    goto run_report
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    goto run_report
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto run_report
)

echo Python 3 was not found. Install Python 3 and try again. 1>&2
exit /b 127

:run_report
"%PYTHON_EXE%" %PYTHON_ARGS% "%SCRIPT_DIR%crisis_dashboard.py" ^
    --countries tr ^
    --as-of 2024-01-31 ^
    --no-web ^
    --event-database "%SCRIPT_DIR%examples\normalized_events.json" ^
    --validate ^
    --source-audit ^
    --output "%SCRIPT_DIR%output\json\fx_cpm_report.json" ^
    --html "%SCRIPT_DIR%output\html\fx_cpm_report.html" ^
    --pdf "%SCRIPT_DIR%output\pdf\fx_cpm_report.pdf" ^
    %*

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo FX-CPM report generation failed with exit code %EXIT_CODE%. 1>&2
    exit /b %EXIT_CODE%
)

echo PDF report: "%SCRIPT_DIR%output\pdf\fx_cpm_report.pdf"
exit /b 0
