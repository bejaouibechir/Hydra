"""
api/studio.py — Sert le Studio (bundle React) depuis l'API.

Le Studio est construit **au moment de la release**, pas à l'installation :
la CI lance `npm run build` puis dépose le résultat dans
`hydra_etl/studio_dist/`, qui voyage dans le wheel comme donnée de paquet.
L'utilisateur final n'a donc besoin ni de Node, ni de npm, ni du dépôt.

Deux règles de montage, dans cet ordre :

1. `/api/...` reste prioritaire — ce module se monte APRÈS les routers.
2. Toute autre URL renvoie `index.html`, parce que le Studio route côté
   navigateur (React Router). Sans ce repli, rafraîchir la page sur
   `/workflows/abc` retournerait un 404.

Si le bundle est absent — dépôt de développement sans build — l'API continue
de fonctionner normalement et `/` affiche la marche à suivre plutôt qu'une
erreur brute.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Chemin du bundle, relatif au paquet installé.
STUDIO_DIST = Path(__file__).resolve().parent.parent / "studio_dist"

# Préfixes réservés à l'API : jamais interceptés par le repli SPA.
_RESERVED = ("/api", "/docs", "/redoc", "/openapi.json")

_MISSING_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Hydra Studio is not bundled</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:44rem;
      margin:12vh auto;padding:0 1.5rem;line-height:1.6;color:#1c1c1c}
 h1{font-size:1.4rem;margin-bottom:.2rem}
 p.sub{color:#666;margin-top:0}
 pre{background:#f4f4f5;padding:.9rem 1rem;border-radius:8px;overflow:auto;
     font-size:.9rem}
 code{background:#f4f4f5;padding:.1rem .35rem;border-radius:4px}
 a{color:#0b6}
</style></head><body>
<h1>Hydra Studio is not bundled in this installation</h1>
<p class="sub">The API is running normally — only the visual editor is missing.</p>
<p>This happens when Hydra runs from a source checkout that has never built the
Studio. A release installed from PyPI ships the bundle already.</p>
<p>Build it once, from the repository root:</p>
<pre>python scripts/build_studio.py</pre>
<p>Then restart <code>hdrctl serve</code>. The API itself needs nothing:
<a href="/api/health">/api/health</a> and <a href="/docs">/docs</a> are live.</p>
</body></html>"""


_DISABLED_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Hydra Studio is disabled</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:44rem;
      margin:12vh auto;padding:0 1.5rem;line-height:1.6;color:#1c1c1c}
 h1{font-size:1.4rem;margin-bottom:.2rem}
 p.sub{color:#666;margin-top:0}
 code{background:#f4f4f5;padding:.1rem .35rem;border-radius:4px}
 a{color:#0b6}
</style></head><body>
<h1>Hydra Studio is disabled on this server</h1>
<p class="sub">The API is running normally.</p>
<p>The server was started with <code>--no-studio</code>, or the environment
variable <code>HYDRA_NO_STUDIO</code> is set. Restart without either one to get
the visual editor back.</p>
<p><a href="/api/health">/api/health</a> · <a href="/docs">/docs</a></p>
</body></html>"""


def studio_status() -> str:
    """Etat du Studio, expose par /api/health pour rendre le diagnostic direct.

    Retourne "bundled", "disabled" ou "missing".
    """
    if studio_is_disabled():
        return "disabled"
    return "bundled" if studio_is_bundled() else "missing"


def studio_is_bundled() -> bool:
    """Vrai si un bundle exploitable est présent."""
    return (STUDIO_DIST / "index.html").is_file()


def studio_is_disabled() -> bool:
    """Vrai si l'utilisateur a demandé une API seule (`hdrctl serve --no-studio`)."""
    import os
    return os.environ.get("HYDRA_NO_STUDIO", "").strip() not in ("", "0", "false", "False")


def studio_root() -> Optional[Path]:
    """Chemin du bundle, ou None s'il est absent."""
    return STUDIO_DIST if studio_is_bundled() else None


def mount_studio(app: FastAPI) -> bool:
    """Monte le Studio sur `/`. Retourne True si le bundle a été trouvé.

    À appeler EN DERNIER, après tous les `include_router`, sinon le montage
    racine capterait les routes de l'API.
    """
    if studio_is_disabled():
        # Meme sans Studio, `/` doit repondre : un 404 JSON sur la racine est
        # indechiffrable pour qui ouvre simplement le navigateur.
        @app.get("/", include_in_schema=False)
        async def _studio_disabled() -> HTMLResponse:  # pragma: no cover
            return HTMLResponse(_DISABLED_PAGE, status_code=200)
        return False

    index = STUDIO_DIST / "index.html"

    if not index.is_file():
        @app.get("/", include_in_schema=False)
        async def _studio_missing() -> HTMLResponse:  # pragma: no cover - trivial
            return HTMLResponse(_MISSING_PAGE, status_code=200)
        return False

    assets = STUDIO_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="studio-assets")

    @app.get("/", include_in_schema=False)
    async def _studio_index() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _studio_spa(full_path: str):
        """Fichier statique s'il existe, sinon index.html (routage React)."""
        if any(("/" + full_path).startswith(p) for p in _RESERVED):
            # Laisse FastAPI répondre son propre 404 : ne jamais renvoyer du
            # HTML à un client qui attend du JSON.
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")

        candidate = (STUDIO_DIST / full_path).resolve()
        try:
            candidate.relative_to(STUDIO_DIST.resolve())
        except ValueError:
            # Tentative de remontée hors du bundle (../../etc/passwd).
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")

        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True
