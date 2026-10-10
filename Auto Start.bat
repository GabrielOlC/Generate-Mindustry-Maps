@echo off
setlocal

REM ============================================================

REM This autostarters REQUIRES any python version installed with PATH

REM  Auto Start - generic launcher for Python projects
REM  1. Goes to the folder where this .bat file is.
REM  2. If .venv is missing: creates it and installs requirements.txt.
REM  3. Asks for optional arguments (unless AUTO_RUN=1), runs SCRIPT with the .venv Python
REM     and closes (unless KEEP_OPEN=1).
REM  To reuse in another project, change only the SCRIPT, AUTO_RUN and KEEP_OPEN lines.

REM ============================================================

REM Change python file Here (only required change!)
set "SCRIPT=wf_generate.py"

REM AUTO_RUN: 1 = run right away, 0 = stop first so you can add arguments (like --seed)
set "AUTO_RUN=1"

REM KEEP_OPEN: 1 = window stays open when the script finishes, 0 = window closes
set "KEEP_OPEN=0"

set "VENV=.venv"
set "REQUIREMENTS=requirements.txt"

REM ============================================================

cd /d "%~dp0"

if not exist "%SCRIPT%" (
    echo Error: %SCRIPT% not found in "%CD%".
    pause
    exit /b 1
)

if not exist "%VENV%\Scripts\python.exe" (
    echo %VENV% not found. Creating the virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 goto :setup_failed

    if exist "%REQUIREMENTS%" (
        echo Installing packages from %REQUIREMENTS%...
        "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%REQUIREMENTS%"
        if errorlevel 1 goto :setup_failed
    ) else (
        echo %REQUIREMENTS% not found. Skipping package installation.
    )
    echo Environment ready.
    echo.
)

REM Show the command and let the user add arguments. Enter alone runs it as is.
set "ARGS="
if not "%AUTO_RUN%"=="1" (
    echo Type extra arguments ^(for example --help^), or press Enter to run as is:
    set /p "ARGS=python %SCRIPT% "
)

"%VENV%\Scripts\python.exe" "%SCRIPT%" %ARGS%
if errorlevel 1 (
    echo.
    echo %SCRIPT% finished with an error.
    pause
    exit /b 1
)
if "%KEEP_OPEN%"=="1" (
    echo.
    echo %SCRIPT% finished.
    pause
)
exit /b 0

:setup_failed
echo.
echo Error: environment setup failed. Removing the incomplete %VENV% so the next run starts clean.
if exist "%VENV%" rmdir /s /q "%VENV%"
pause
exit /b 1
