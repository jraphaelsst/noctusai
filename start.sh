#!/bin/bash
# Start script for Replit - runs both backend and frontend

echo "🚀 Starting Corretor Goal Hub..."

# Install Python dependencies if needed
if [ ! -d "backend/venv" ]; then
  echo "📦 Installing Python dependencies..."
  cd backend
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  cd ..
else
  source backend/venv/bin/activate
fi

# Install Node dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
  echo "📦 Installing Node dependencies..."
  cd frontend
  npm install
  cd ..
fi

# Start backend on port 8000 (background)
echo "🐍 Starting FastAPI backend on port 8000..."
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Start frontend on port 5173
echo "⚛️  Starting React frontend on port 5173..."
cd frontend
VITE_BACKEND_API_URL=http://localhost:8000 npx vite --host 0.0.0.0 --port 5173

# Cleanup
kill $BACKEND_PID 2>/dev/null
