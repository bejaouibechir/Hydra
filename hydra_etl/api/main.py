"""
api/main.py — Application FastAPI principale pour Hydra ETL.

Démarrage :
    hdrctl serve                         # via CLI (recommandé)
    uvicorn api.main:app --reload        # direct
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hydra_etl import __version__

from hydra_etl.api.routers import (
    health,
    projects,
    workflows,
    runs,
    environments,
    nodes,
    templates,
    jobs,
    system,
    fs,
    export,
    terminal,
    transform,
    parameters,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Démarre/arrête le scheduler des triggers `schedule` avec l'API."""
    from hydra_etl.api import scheduler
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title="Hydra ETL API",
    description="API REST pour piloter les jobs et workflows Hydra ETL.",
    version=__version__,   # Règle 3.1
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — permissif en v1 (Studio tourne sur localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router,       tags=["Health"])
app.include_router(projects.router,     prefix="/api/projects",     tags=["Projects"])
app.include_router(workflows.router,    prefix="/api/workflows",    tags=["Workflows"])
app.include_router(runs.router,         prefix="/api/runs",         tags=["Runs"])
app.include_router(environments.router, prefix="/api/environments", tags=["Environments"])
app.include_router(nodes.router,        prefix="/api/nodes",        tags=["Nodes"])
app.include_router(templates.router,    prefix="/api/templates",    tags=["Templates"])
app.include_router(jobs.router,         prefix="/api/jobs",         tags=["Jobs"])
app.include_router(system.router,       prefix="/api/system",       tags=["System"])
app.include_router(fs.router,           prefix="/api/fs",           tags=["Filesystem"])
app.include_router(export.router,       prefix="/api/export",       tags=["Export"])
app.include_router(terminal.router,     prefix="/api/terminal",     tags=["Terminal"])
app.include_router(transform.router,    prefix="/api/transform",    tags=["Transform"])
app.include_router(parameters.router,   prefix="/api/parameters",   tags=["Parameters"])

# Studio — TOUJOURS en dernier : le montage racine capterait sinon les routes
# ci-dessus. Sans bundle, l'API reste entièrement fonctionnelle.
from hydra_etl.api.studio import mount_studio  # noqa: E402

STUDIO_BUNDLED = mount_studio(app)
