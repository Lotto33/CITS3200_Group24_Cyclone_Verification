#!/bin/bash
set -e

echo "Preparing persistent storage..."

export DATA_DIR="${DATA_DIR:-/home/cyclone/data}"

mkdir -p "$DATA_DIR/gml"
mkdir -p "$DATA_DIR/uploads"
mkdir -p "$DATA_DIR/geojson"

echo "Generating map configuration..."
python backend/app/build_map_config.py --out-dir "$DATA_DIR"

cd backend

echo "Running database migrations..."
python -m alembic upgrade head

echo "Starting FastAPI..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000