from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401
from app.config import settings
from app.routers import assistant, auth, billing, calendar, focus, health, tasks, voice

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

app = FastAPI(
    title=settings.APP_NAME,
    description="Voice-first knowledge operating system",
    version="0.1.0",
    debug=settings.DEBUG,
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
app.include_router(focus.router, prefix="/focus", tags=["focus"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
        "tagline": "Capture thought. Connect knowledge. Create impact.",
        "ui": "/app",
        "billing": "/billing/plans",
    }


@app.get("/app")
def app_shell():
    """Tek sütun arayüz (statik HTML)."""
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "static/index.html bulunamadı")
    return FileResponse(index)
