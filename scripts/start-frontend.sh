#!/bin/bash

# BTflow Studio Frontend Startup Script

echo "🎨 Starting BTflow Studio Frontend..."

# Kill any existing process on port 5173
lsof -ti:5173 | xargs kill -9 2>/dev/null

# Navigate to frontend directory and start dev server
cd btflow-studio/frontend
npm run dev
