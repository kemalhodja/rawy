# Rawy

Voice-first knowledge platform backend (FastAPI + SQLAlchemy + Alembic).

## Project Structure

```text
rawy/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── voice.py
│   │   └── health.py
│   └── services/
│       ├── __init__.py
│       ├── whisper_service.py
│       └── storage.py
├── alembic/
├── tests/
├── uploads/
├── .env.example
├── .gitignore
├── requirements.txt
└── docker-compose.yml
```

## Quick Start

1) Install dependencies:

```bash
python -m pip install -r requirements.txt
```

2) Create env file:

```bash
cp .env.example .env
```

3) Start database services:

```bash
docker compose up -d db redis
```

4) Run migrations:

```bash
python -m alembic upgrade head
```

5) Start API:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Local Test

```bash
python -m pytest tests/ -q
```

## PostgreSQL Smoke

```bash
# 1) PostgreSQL acik olmali (docker compose up -d db)
# 2) DATABASE_URL PostgreSQL'e isaret etmeli
DATABASE_URL=postgresql://rawy:rawy@localhost:5432/rawy python scripts/smoke_pg.py
```

## Notes

- `uploads/` contains user audio files and is ignored by git except `.gitkeep`.
- Upload size limiti `MAX_UPLOAD_SIZE` ile zorlanir (`app/services/storage.py`).
- Multipart upload icin `python-multipart` dependency zorunludur.
- SQLite is supported for local smoke tests via:

```bash
DATABASE_URL=sqlite:///./rawy.db python -m alembic upgrade head
```
