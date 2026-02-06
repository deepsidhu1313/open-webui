#!/bin/bash

# Function to handle kill signal
cleanup() {
    echo "Stopping services..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGTERM SIGINT

echo "🚀 Starting Open-WebUI Development Environment"
echo "mode: Build-on-Start"

# Fix git dubios ownership issues in container
git config --global --add safe.directory /app


# 1. Build Frontend in Watch Mode
echo "📦 [Frontend] Installing dependencies..."
npm install --legacy-peer-deps

echo "👀 [Frontend] Starting Build Watch Mode..."
echo "   (Initial build may take a minute...)"
# Run build:watch in background so backend can start
npm run build
# FRONTEND_PID=$!

# Wait a bit for initial build to produce something (optional, but good for UX)
# sleep 10

echo "✅ [Frontend] Watch mode started. Updates will trigger rebuilds."

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
