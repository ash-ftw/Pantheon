from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    admin_routes,
    auth_routes,
    defense_routes,
    lab_routes,
    report_routes,
    scenario_routes,
    simulation_routes,
    target_app_routes,
    template_routes,
)
from app.config import settings
from app.database import SessionLocal, init_db
from app.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        init_db()
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(
    title="Pantheon API",
    description="FastAPI backend for the Pantheon Kubernetes cyber-range.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": "Pantheon",
        "mode": settings.kubernetes_mode,
    }


app.include_router(auth_routes.router, prefix=settings.api_prefix)
app.include_router(template_routes.router, prefix=settings.api_prefix)
app.include_router(scenario_routes.router, prefix=settings.api_prefix)
app.include_router(lab_routes.router, prefix=settings.api_prefix)
app.include_router(simulation_routes.router, prefix=settings.api_prefix)
app.include_router(target_app_routes.router, prefix=settings.api_prefix)
app.include_router(defense_routes.router, prefix=settings.api_prefix)
app.include_router(report_routes.router, prefix=settings.api_prefix)
app.include_router(admin_routes.router, prefix=settings.api_prefix)

_frontend_candidates = [
    Path(__file__).resolve().parents[2] / "frontend",
    Path(__file__).resolve().parents[1] / "frontend",
]
FRONTEND_DIR = next((candidate for candidate in _frontend_candidates if candidate.exists()), _frontend_candidates[0])
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="frontend-assets")


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{asset_name}")
def dashboard_asset(asset_name: str) -> FileResponse:
    asset_path = FRONTEND_DIR / asset_name
    if asset_path.exists() and asset_path.is_file():
        return FileResponse(asset_path)
    return FileResponse(FRONTEND_DIR / "index.html")
