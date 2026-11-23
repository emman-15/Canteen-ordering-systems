#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo "  Canteen System - Starting..."
echo "============================================"
echo

# Pick a python command that exists
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "ERROR: Python was not found. Please install Python 3 from https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

# Create the virtual environment if it does not exist yet
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating virtual environment, please wait..."
    $PYTHON -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing/checking dependencies..."
pip install -r requirements.txt --quiet

echo
echo "============================================"
echo "  Launching app at http://localhost:5000"
echo "  Keep this window open while using the app."
echo "  Press CTRL+C to stop the server."
echo "============================================"
echo

# Open the browser after a short delay, then start the server
( sleep 2 && (open http://localhost:5000 2>/dev/null || xdg-open http://localhost:5000 2>/dev/null) ) &

python app.py
