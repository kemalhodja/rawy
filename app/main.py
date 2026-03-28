from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401
from app.config import settings
from app.routers import api, assistant, auth, billing, calendar, focus, graph, health, meetings, reminders, saml, speaker, tasks, voice, workspace

# Static dosya dizinini bul
ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

# Eğer static klasörü yoksa, çalışma dizininde dene
if not STATIC_DIR.is_dir():
    STATIC_DIR = Path("/app/static")
if not STATIC_DIR.is_dir():
    STATIC_DIR = Path.cwd() / "static"

print(f"Static directory: {STATIC_DIR} (exists: {STATIC_DIR.is_dir()})")

app = FastAPI(
    title=settings.APP_NAME,
    description="Voice-first knowledge operating system",
    version="0.1.0",
    debug=settings.DEBUG,
)

# CORS - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static dosyaları mount et
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    print(f"Static files mounted at: {STATIC_DIR}")
else:
    print(f"WARNING: Static directory not found: {STATIC_DIR}")

app.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
app.include_router(focus.router, prefix="/focus", tags=["focus"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(reminders.router, prefix="/reminders", tags=["reminders"])
app.include_router(graph.router, tags=["knowledge-graph"])
app.include_router(workspace.router, tags=["workspaces"])
app.include_router(api.router)
app.include_router(saml.router)
app.include_router(meetings.router)
app.include_router(speaker.router)


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
    print(f"Looking for index.html at: {index} (exists: {index.is_file()})")
    
    if not index.is_file():
        # Alternatif konumları dene
        alt_paths = [
            Path("/app/static/index.html"),
            Path.cwd() / "static" / "index.html",
            ROOT_DIR / "static" / "index.html",
        ]
        for alt in alt_paths:
            print(f"Trying alternative: {alt} (exists: {alt.is_file()})")
            if alt.is_file():
                return FileResponse(alt)
        
        raise HTTPException(404, f"static/index.html not found. Searched: {index}, {alt_paths}")
    
    return FileResponse(index)


@app.get("/debug/static")
def debug_static():
    """Static dosya yollarını debug et"""
    paths = {
        "ROOT_DIR": str(ROOT_DIR),
        "STATIC_DIR": str(STATIC_DIR),
        "STATIC_DIR_exists": STATIC_DIR.is_dir(),
        "index_html": str(STATIC_DIR / "index.html"),
        "index_html_exists": (STATIC_DIR / "index.html").is_file(),
        "cwd": str(Path.cwd()),
        "cwd_static_exists": (Path.cwd() / "static").is_dir(),
    }
    
    # Tüm dosyaları listele
    files = []
    if STATIC_DIR.is_dir():
        try:
            files = [str(f.name) for f in STATIC_DIR.iterdir()][:20]
        except Exception as e:
            files = [f"Error: {e}"]
    
    return {
        "paths": paths,
        "static_files": files,
        "manifest_exists": (STATIC_DIR / "manifest.json").is_file(),
    }


@app.get("/test-html")
def test_html():
    """Basit HTML test"""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Rawy Test</title></head>
    <body>
        <h1>Rawy Çalışıyor!</h1>
        <p>API bağlantısı test ediliyor...</p>
        <script>
            fetch('/health').then(r => r.json()).then(d => {
                document.body.innerHTML += '<p style="color:green">✅ API OK: ' + JSON.stringify(d) + '</p>';
            }).catch(e => {
                document.body.innerHTML += '<p style="color:red">❌ API Hatası: ' + e + '</p>';
            });
        </script>
    </body>
    </html>
    """
