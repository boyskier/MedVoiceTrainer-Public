@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  MedVoiceTrainer Build Script
echo ============================================================
echo.

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)
python --version
echo [OK] Python found
echo.

REM Install dependencies
echo [1/4] Installing packages...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pip install failed. Check internet connection.
    pause
    exit /b 1
)
python -m pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    python -m pip install pyinstaller --quiet
)
echo [OK] Packages installed
echo.

REM Run tests
echo [2/4] Running tests...
python -m pytest tests/ -q --tb=short
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Some tests failed. Continue? (Y/N)
    set /p CONT=
    if /i "!CONT!" NEQ "Y" (
        echo Build cancelled.
        pause
        exit /b 1
    )
)
echo [OK] Tests done
echo.

REM Clean previous build
echo [3/4] Building executable...
if exist "dist\MedVoiceTrainer" rmdir /s /q "dist\MedVoiceTrainer"
if exist "build" rmdir /s /q "build"

python -m PyInstaller --noconfirm --onedir --windowed --name MedVoiceTrainer --exclude-module tkinter.test --exclude-module unittest --exclude-module xmlrpc --exclude-module email --exclude-module html --exclude-module http --exclude-module urllib --exclude-module multiprocessing --exclude-module concurrent --exclude-module numpy.testing --exclude-module matplotlib.tests --exclude-module scipy --noupx main.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller failed.
    pause
    exit /b 1
)
echo [OK] Executable built
echo.

REM Package data files
echo [4/4] Packaging data files...
set DIST_DIR=dist\MedVoiceTrainer

if exist "data" (
    xcopy "data" "%DIST_DIR%\data\" /E /I /Q /Y
    echo [OK] data/ copied
)

if not exist "%DIST_DIR%\.env" (
    if exist ".env" (
        copy ".env" "%DIST_DIR%\.env" >nul
    ) else (
        echo GEMINI_API_KEY=> "%DIST_DIR%\.env"
        echo ANTHROPIC_API_KEY=>> "%DIST_DIR%\.env"
        echo OPENAI_API_KEY=>> "%DIST_DIR%\.env"
    )
    echo [OK] .env placed
)

if not exist "%DIST_DIR%\db\backups" mkdir "%DIST_DIR%\db\backups"
if not exist "%DIST_DIR%\db\cost_reports" mkdir "%DIST_DIR%\db\cost_reports"
if not exist "%DIST_DIR%\data\custom" mkdir "%DIST_DIR%\data\custom"

if exist "USER_GUIDE_KO.md" (
    copy "USER_GUIDE_KO.md" "%DIST_DIR%\USER_GUIDE_KO.md" >nul
    echo [OK] User guide copied
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo ============================================================
echo.
echo  Executable: %CD%\%DIST_DIR%\MedVoiceTrainer.exe
echo.
echo  IMPORTANT: Edit .env before running:
echo    %CD%\%DIST_DIR%\.env
echo  Add your GEMINI_API_KEY and ANTHROPIC_API_KEY
echo.
echo  Press any key to launch...
pause >nul
start "" "%DIST_DIR%\MedVoiceTrainer.exe"
