#!/bin/bash

echo "================================"
echo "VK Ads Manager - Web Interface"
echo "================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Start backend
echo "Starting backend API server..."
cd "$SCRIPT_DIR/backend/api"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start frontend
echo "Starting frontend dev server..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "================================"
echo "Servers started!"
echo "Backend API:  http://localhost:8000"
echo "Frontend:     http://localhost:5173"
echo "API Docs:     http://localhost:8000/docs"
echo "================================"
echo ""
echo "Press Ctrl+C to stop all servers"

# Handle Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

# Wait for processes
wait
