#!/bin/bash

# Function to handle kill signal
cleanup() {
    echo "Stopping services..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGTERM SIGINT

echo "🚀 Starting Open-WebUI Development Environment"

# Fix git dubious ownership issues in container
git config --global --add safe.directory /app

# 1. Frontend
echo "📦 [Frontend] Installing dependencies..."
npm install --legacy-peer-deps

if [ "${FORCE_BUILD}" = "true" ] || [ ! -d "build" ]; then
    echo "🔨 [Frontend] Building... (set FORCE_BUILD=true to always rebuild)"
    npm run build
    echo "✅ [Frontend] Build complete."
else
    echo "⚡ [Frontend] Skipping build — 'build/' exists (FORCE_BUILD not set)."
fi

# 2. Install and Start Backend
echo "🐍 [Backend] Installing Python dependencies..."
cd backend
pip install -r requirements.txt

echo "⚙️ [Backend] Starting Backend Server..."
# The backend will verify /app/build exists and serve it
./start.sh &
BACKEND_PID=$!

# Wait for process
echo "✅ Service is ready at: http://localhost:8080"
echo "   (Frontend will refresh automatically after rebuilds)"
wait $BACKEND_PID
