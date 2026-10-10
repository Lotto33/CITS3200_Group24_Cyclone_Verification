#!/bin/bash
set -e

echo "Preparing persistent storage..."

mkdir -p /home/cyclone/data/gml
mkdir -p /home/cyclone/data/uploads
mkdir -p /home/cyclone/data/geojson

echo "Generating map configuration..."
python backend/app/build_map_config.py --out-dir /home/cyclone/data

cd backend

echo "Running database migrations..."
python -m alembic upgrade head

echo "Starting FastAPI..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000