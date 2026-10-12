FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    DATABASE_URL=sqlite+pysqlite:////app/data/cyclone.db

# The repo layout is kept under /app: the backend resolves frontend/ (the HTML
# pages and assets/) and data/ relative to its own source location.
WORKDIR /app

# Dependencies first so this layer is cached across code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY backend ./backend
COPY frontend/assets ./frontend/assets
COPY frontend/*.html ./frontend/
COPY startup.sh ./

# Editable install keeps the package at /app/backend (not site-packages).
RUN pip install --no-deps -e backend

VOLUME /app/data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["bash", "startup.sh"]
