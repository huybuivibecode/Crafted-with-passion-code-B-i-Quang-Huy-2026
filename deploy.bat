@echo off
echo ========================================================
echo   BurgerPrintsAgent Deployment ^& Setup Script (Windows)
echo ========================================================

REM 1. Check Python installation
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    exit /b 1
)

REM 2. Create python virtual environment
if not exist venv (
    echo [INFO] Creating Python virtual environment (venv)...
    python -m venv venv
) else (
    echo [INFO] virtual environment (venv) already exists.
)

REM 3. Activate venv and install requirements
echo [INFO] Activating virtual environment and installing python dependencies...
call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

REM 4. Create .env file template if it doesn't exist
if not exist .env (
    echo [INFO] Creating .env file from template...
    echo DJANGO_SECRET_KEY=django-insecure-burgerprints-agent-dev-key-change-in-prod > .env
    echo DEBUG=True >> .env
    echo BURGER_PRINTS_API_KEY=your_burgerprints_api_key_here >> .env
    echo GEMINI_API_KEY=your_gemini_api_key_here >> .env
    echo GEMINI_MODEL=gemini-2.0-flash >> .env
    echo CATALOG_CACHE_TTL=300 >> .env
    echo [WARNING] Please open .env and fill in your actual BURGER_PRINTS_API_KEY and GEMINI_API_KEY!
) else (
    echo [INFO] .env file already exists.
)

REM 5. Run migrations
echo [INFO] Running database migrations...
python manage.py migrate

REM 6. Build React frontend if Node.js is installed
where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Node.js detected. Building React frontend...
    cd frontend
    call npm install
    call npm run build
    cd ..
    
    echo [INFO] Copying assets to Django...
    if not exist static\assets mkdir static\assets
    xcopy /y /e /s /i frontend\dist\assets\* static\assets\
    copy /y frontend\dist\index.html templates\agent\chat.html
    echo [SUCCESS] React frontend built and copied successfully!
) else (
    echo [WARNING] Node.js/npm not found. Skipping React build. (Using existing build static files)
)

echo [SUCCESS] Setup complete! Starting Django server...
python manage.py runserver 0.0.0.0:8000
