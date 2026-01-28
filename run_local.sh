#!/bin/bash
# Local testing script for Via Web App
# This script helps you test the app locally before pushing to GitHub

echo "🚀 Starting Via Web App locally..."
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

VENV_DIR="venv"
PYTHON_CMD="python3"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment."
        echo ""
        echo "Please ensure python3-venv is installed:"
        echo "  On macOS: brew install python3"
        echo "  On Ubuntu/Debian: sudo apt-get install python3-venv"
        exit 1
    fi
    echo "✅ Virtual environment created!"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Check if streamlit is installed
if ! python -m streamlit --version > /dev/null 2>&1; then
    echo "📥 Installing dependencies..."
    echo ""
    
    # Upgrade pip first
    python -m pip install --upgrade pip > /dev/null 2>&1
    
    # Install requirements
    if python -m pip install -r requirements.txt; then
        echo ""
        echo "✅ Dependencies installed!"
    else
        echo ""
        echo "❌ Failed to install dependencies."
        echo ""
        echo "Please check requirements.txt and try again."
        exit 1
    fi
fi

echo ""
echo "✅ Environment ready!"
echo ""
echo "Make sure you have created openai_secrets.json with your API key"
echo "(The script will check this when starting)"
echo ""
echo "Starting Streamlit..."
echo ""

python -m streamlit run via_web_app.py
