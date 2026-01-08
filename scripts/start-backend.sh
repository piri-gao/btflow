#!/bin/bash

# BTflow Studio Backend Startup Script

echo "🚀 Starting BTflow Studio Backend..."

# Activate conda environment
eval "$(conda shell.zsh hook)"
conda activate pytree

# Set PYTHONPATH to include project root
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Install dependencies if needed
pip install -q websockets uvicorn fastapi pydantic

# Start backend
cd btflow-studio
python -m backend.app.main
