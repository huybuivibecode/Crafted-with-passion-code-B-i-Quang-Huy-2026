#!/bin/bash
set -e

echo "========================================================"
echo "  BurgerPrintsAgent Deployment & Setup Script (Bash)"
echo "========================================================"

# 1. Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 is not installed or not in PATH!"
    exit 1
fi

# 2. Create python virtual environment
if [ ! -d "venv" ]; then
    echo "[INFO] Creating Python virtual environment (venv)..."
    python3 -m venv venv
else
    echo "[INFO] virtual environment (venv) already exists."
fi

# 3. Activate venv and install requirements
echo "[INFO] Activating virtual environment and installing python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create .env file template if it doesn't exist
if [ ! -f ".env" ]; then
    echo "[INFO] Creating .env file from template..."
    echo "DJANGO_SECRET_KEY=django-insecure-burgerprints-agent-dev-key-change-in-prod" > .env
    echo "DEBUG=True" >> .env
    echo "BURGER_PRINTS_API_KEY=your_burgerprints_api_key_here" >> .env
    echo "GEMINI_API_KEY=your_gemini_api_key_here" >> .env
    echo "GEMINI_MODEL=gemini-2.0-flash" >> .env
    echo "CATALOG_CACHE_TTL=300" >> .env
    echo "[WARNING] Please open .env and fill in your actual BURGER_PRINTS_API_KEY and GEMINI_API_KEY!"
else
    echo "[INFO] .env file already exists."
fi

# 5. Run migrations
echo "[INFO] Running database migrations..."
python manage.py migrate

# 6. Build React frontend if Node.js is installed
if command -v npm &> /dev/null; then
    echo "[INFO] Node.js detected. Building React frontend..."
    cd frontend
    npm install
    npm run build
    cd ..
    
    echo "[INFO] Copying assets to Django..."
    mkdir -p static/assets
    cp -r frontend/dist/assets/* static/assets/
    cp frontend/dist/index.html templates/agent/chat.html
    echo "[SUCCESS] React frontend built and copied successfully!"
else
    echo "[WARNING] Node.js/npm not found. Skipping React build. (Using existing build static files)"
fi

echo "[SUCCESS] Setup complete! Starting Django server..."
python manage.py runserver 0.0.0.0:8000
