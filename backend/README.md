# Backend (FastAPI)

Skeleton FastAPI service, structured following common FastAPI conventions
(routers versioned under `app/api/v1/`, config/settings under `app/core/`,
persistence layers split into `app/models/` and `app/schemas/`, business
logic in `app/services/`).

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI() app instance, mounts routers
│   ├── api/
│   │   ├── deps.py          # shared dependencies (get_db, auth, ...)
│   │   └── v1/
│   │       ├── router.py    # aggregates all v1 endpoint routers
│   │       └── endpoints/   # one module per resource (e.g. cyclones.py)
│   ├── core/
│   │   └── config.py        # Settings (env vars / .env)
│   ├── models/               # ORM models
│   ├── schemas/               # Pydantic request/response models
│   ├── services/               # business logic
│   └── db/
│       └── session.py        # DB engine/session setup
└── tests/
```

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload
```

- Docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Test

```bash
pytest
```

## Adding a new resource

1. Add a Pydantic schema in `app/schemas/`.
2. Add an ORM model in `app/models/` if it's persisted.
3. Add business logic in `app/services/`.
4. Add an endpoint module in `app/api/v1/endpoints/`, then register it in
   `app/api/v1/router.py`.
