"""
api/store.py — Persistance YAML sur disk pour Hydra v1 (pas de base de données).

Modèle physique canonique (aligné CLI ↔ Studio) :
  project/                    ← 1 projet = 1 dossier (aucun fichier manifest requis)
  ├── Data/                   ← données d'input (convention, optionnel)
  ├── output/                 ← résultats générés par les jobs (convention)
  ├── workflows/<nom>.yaml    ← 1 workflow = 1 fichier YAML (ordre des jobs)
  ├── jobs/<nom>/             ← 1 job = 1 dossier avec 4 fichiers YAML
  │   ├── sources.yaml
  │   ├── transformations.yaml
  │   ├── destinations.yaml
  │   └── pipeline.yaml
  └── .hydra/                 ← métadonnées internes Studio (hors conception :
      ├── project.json           id, nom, registre — invisible pour l'utilisateur)
      └── workflows/<id>.json    layout canvas, méta workflow

Un projet est reconnu par sa STRUCTURE (workflows/*.yaml ou jobs/*/pipeline.yaml),
pas par un fichier manifest. Rétro-compatibilité : anciens projets
(.hydra_project.json + workflows/<id>/workflow.yaml) et project.yaml
(versions intermédiaires) restent lisibles.

  - runs         : en mémoire (perte au redémarrage — acceptable en v1)
  - environments : fichiers .env.<nom> dans le dossier project
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from hydra_etl.internal.fs_atomic import atomic_write_text
from hydra_etl.api.models import (
    EnvironmentResponse,
    ProjectResponse,
    RunResponse,
    WorkflowResponse,
)

# Répertoire racine de tous les projets Studio
WORKSPACE = Path(os.environ.get("HYDRA_WORKSPACE", Path.home() / "hydra-workspace"))
WORKSPACE.mkdir(parents=True, exist_ok=True)

# Index des projets (inclut les projets hors WORKSPACE)
# Format : { project_id: "/chemin/absolu/vers/le/projet" }
_INDEX_FILE = WORKSPACE / "projects.index.json"

# Store en mémoire pour les runs (volatile)
_runs: Dict[str, RunResponse] = {}

# Projets retirés de la liste (raccourci supprimé, dossier conservé) —
# empêche le scan du WORKSPACE de les faire réapparaître
_HIDDEN_FILE = WORKSPACE / "projects.hidden.json"


def _load_hidden() -> set:
    if not _HIDDEN_FILE.exists():
        return set()
    try:
        return set(json.loads(_HIDDEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_hidden(ids: set) -> None:
    atomic_write_text(_HIDDEN_FILE, json.dumps(sorted(ids)))

STUDIO_DIR = ".hydra"


def _load_index() -> Dict[str, str]:
    if not _INDEX_FILE.exists():
        return {}
    try:
        return json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(index: Dict[str, str]) -> None:
    atomic_write_text(_INDEX_FILE, json.dumps(index, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(name: str) -> str:
    """Nom de fichier/dossier sûr à partir d'un nom utilisateur."""
    s = name.strip().lower().replace(" ", "_")
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    return s or "unnamed"


def _project_path(project_id: str) -> Path:
    """Chemin par défaut dans WORKSPACE (legacy / projets internes)."""
    return WORKSPACE / project_id


def _resolve_project_path(project_id: str) -> Path:
    """Chemin réel du projet — consulte l'index, fallback sur WORKSPACE."""
    index = _load_index()
    if project_id in index:
        return Path(index[project_id])
    return WORKSPACE / project_id


def _meta_file(project_id: str) -> Path:
    """Méta legacy (.hydra_project.json) — conservé en lecture."""
    return _resolve_project_path(project_id) / ".hydra_project.json"


# ---------------------------------------------------------------------------
# Méta Studio : .hydra/project.json (interne — le projet reste un simple dossier)
# ---------------------------------------------------------------------------

def _studio_meta_file(project_path: Path) -> Path:
    return project_path / STUDIO_DIR / "project.json"


def _read_manifest(project_path: Path) -> Optional[dict]:
    # 1. Méta Studio courante
    f = _studio_meta_file(project_path)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 2. Compat : project.yaml créé par une version intermédiaire
    f2 = project_path / "project.yaml"
    if f2.exists():
        try:
            doc = yaml.safe_load(f2.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("project"), dict):
                return doc["project"]
        except Exception:
            pass
    return None


def _write_manifest(project_path: Path, manifest: dict) -> None:
    f = _studio_meta_file(project_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(f, json.dumps(manifest, indent=2, ensure_ascii=False))


def _looks_like_hydra_project(path: Path) -> bool:
    """Reconnaissance par la STRUCTURE — c'est ça, un projet Hydra :
    des workflows (fichiers YAML) et/ou des jobs (dossiers à 4 YAML)."""
    wf = path / "workflows"
    if wf.is_dir() and (any(wf.glob("*.yaml")) or any(wf.glob("*.yml"))):
        return True
    jobs = path / "jobs"
    if jobs.is_dir():
        for d in jobs.iterdir():
            if d.is_dir() and (d / "pipeline.yaml").exists():
                return True
    return False


def _register_workflow_in_manifest(project_path: Path, wf_id: str, name: str, rel_file: str) -> None:
    m = _read_manifest(project_path)
    if m is None:
        return
    wfs = [w for w in m.get("workflows", []) if w.get("id") != wf_id]
    wfs.append({"id": wf_id, "name": name, "file": rel_file})
    m["workflows"] = wfs
    _write_manifest(project_path, m)


def _unregister_workflow_in_manifest(project_path: Path, wf_id: str) -> None:
    m = _read_manifest(project_path)
    if m is None:
        return
    m["workflows"] = [w for w in m.get("workflows", []) if w.get("id") != wf_id]
    _write_manifest(project_path, m)


def _register_job_in_manifest(project_path: Path, name: str, rel_dir: str) -> None:
    m = _read_manifest(project_path)
    if m is None:
        return
    jobs = [j for j in m.get("jobs", []) if j.get("name") != name]
    jobs.append({"name": name, "path": rel_dir})
    m["jobs"] = jobs
    _write_manifest(project_path, m)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def _project_from_path(project_path: Path) -> Optional[ProjectResponse]:
    """Lit un projet : project.yaml (canonique) puis .hydra_project.json (legacy)."""
    m = _read_manifest(project_path)
    if m is not None:
        try:
            return ProjectResponse(
                id=m.get("id", ""),
                name=m.get("name", project_path.name),
                description=m.get("description"),
                path=str(project_path),
                created_at=m.get("created_at", ""),
            )
        except Exception:
            pass
    meta = project_path / ".hydra_project.json"
    if meta.exists():
        try:
            return ProjectResponse(**json.loads(meta.read_text(encoding="utf-8")))
        except Exception:
            pass
    return None


def list_projects() -> List[ProjectResponse]:
    result = []
    seen: set = set()
    index = _load_index()

    # 1. Projets enregistrés dans l'index (inclut les projets hors WORKSPACE)
    for project_id, path_str in index.items():
        proj = _project_from_path(Path(path_str))
        if proj:
            result.append(proj)
            seen.add(project_id)

    # 2. Projets legacy dans WORKSPACE non encore indexés (rétrocompat)
    hidden = _load_hidden()
    for p in sorted(WORKSPACE.iterdir()):
        if not p.is_dir():
            continue
        proj = _project_from_path(p)
        if proj and proj.id not in seen and proj.id not in hidden:
            result.append(proj)

    return sorted(result, key=lambda r: r.created_at)


def get_project(project_id: str) -> Optional[ProjectResponse]:
    return _project_from_path(_resolve_project_path(project_id))


def create_project(name: str, description: Optional[str] = None, project_path: Optional[str] = None) -> ProjectResponse:
    project_id = str(uuid.uuid4())[:8]

    # Chemin du projet : basé sur le NOM (slug) — plus lisible pour l'humain.
    #   - project_path fourni → {project_path}/{slug}/
    #   - sinon               → {WORKSPACE}/{slug}/
    # En cas de collision de nom, on suffixe avec l'id court pour rester unique.
    base = Path(project_path) if project_path else WORKSPACE
    slug = _slug(name)
    path = base / slug
    if path.exists():
        path = base / f"{slug}-{project_id}"

    # Structure canonique du projet
    for subdir in ["workflows", "jobs", "Data", "output", ".hydra/workflows"]:
        (path / subdir).mkdir(parents=True, exist_ok=True)

    created = _now()
    _write_manifest(path, {
        "id": project_id,
        "name": name,
        "description": description or "",
        "created_at": created,
        "conventions": {
            "data_dir": "Data",      # données d'input (optionnel — l'utilisateur reste libre)
            "output_dir": "output",  # résultats générés par les jobs
        },
        "workflows": [],
        "jobs": [],
    })

    proj = ProjectResponse(
        id=project_id,
        name=name,
        description=description,
        path=str(path),
        created_at=created,
    )

    # Enregistre dans l'index (nécessaire pour les projets hors WORKSPACE)
    index = _load_index()
    index[project_id] = str(path)
    _save_index(index)

    return proj


def delete_project(project_id: str, remove_files: bool = True) -> bool:
    """Supprime un projet — IDEMPOTENT : retirer de la liste ne peut pas échouer.

    remove_files=False → retire uniquement le raccourci de la liste
                          (le dossier reste intact sur le disk)
    remove_files=True  → retire le raccourci ET supprime le dossier physique

    Gère tous les états dégradés : entrée d'index dont la clé ne correspond
    plus à l'id de la méta, dossier déjà supprimé à la main, méta orpheline.
    """
    index = _load_index()

    # Résoudre le chemin : clé d'index directe, sinon recherche par id de méta
    path: Optional[Path] = None
    if project_id in index:
        path = Path(index[project_id])
    else:
        for key, pstr in list(index.items()):
            proj = _project_from_path(Path(pstr))
            if proj and proj.id == project_id:
                path = Path(pstr)
                index.pop(key, None)     # purge l'entrée même si sa clé diffère
                break
        if path is None:
            candidate = _project_path(project_id)
            if candidate.exists():
                path = candidate

    if remove_files and path and path.exists():
        import shutil
        shutil.rmtree(path, ignore_errors=True)

    index.pop(project_id, None)
    _save_index(index)

    hidden = _load_hidden()
    if remove_files:
        hidden.discard(project_id)      # plus rien à cacher
    else:
        hidden.add(project_id)          # ne pas réapparaître via le scan WORKSPACE
    _save_hidden(hidden)
    return True


class NotAHydraProject(Exception):
    """Le dossier ne contient ni project.yaml ni méta legacy."""


def open_project(path_str: str, adopt: bool = True) -> Optional[ProjectResponse]:
    """Ouvre/importe un projet existant depuis le disk.

    - project.yaml présent          → lit le manifest, enregistre dans l'index
    - .hydra_project.json (legacy)  → idem
    - dossier quelconque            → « adoption » : crée project.yaml + structure standard
    Accepte un dossier OU le chemin direct de project.yaml.
    """
    path = Path(path_str)
    if path.is_file():                      # l'utilisateur a sélectionné project.yaml
        path = path.parent
    if not path.is_dir():
        return None

    proj = _project_from_path(path)
    if proj is None:
        # Pas de méta Studio — projet reconnu par sa structure, sinon adoption
        if not adopt and not _looks_like_hydra_project(path):
            raise NotAHydraProject(str(path))
        # Enregistrement (structure reconnue) ou adoption (dossier quelconque) —
        # ne crée que les dossiers manquants, n'écrase jamais l'existant
        project_id = str(uuid.uuid4())[:8]
        for subdir in ["workflows", "jobs", "Data", "output", ".hydra/workflows"]:
            (path / subdir).mkdir(parents=True, exist_ok=True)
        created = _now()
        _write_manifest(path, {
            "id": project_id,
            "name": path.name,
            "description": "",
            "created_at": created,
            "conventions": {"data_dir": "Data", "output_dir": "output"},
            "workflows": [],
            "jobs": [],
        })
        proj = ProjectResponse(id=project_id, name=path.name, description="",
                               path=str(path), created_at=created)

    index = _load_index()
    index[proj.id] = str(path)
    _save_index(index)

    # Ré-ouvrir un projet précédemment retiré de la liste → le dé-cacher
    hidden = _load_hidden()
    if proj.id in hidden:
        hidden.discard(proj.id)
        _save_hidden(hidden)

    # Découverte : enregistrer les workflows/jobs déjà présents sur disk
    _discover_disk_content(path, proj.id)
    return proj


def _discover_disk_content(project_path: Path, project_id: str) -> None:
    """Enregistre dans Studio les workflows/*.yaml et jobs/*/ créés à la main.

    Symétrie CLI ↔ Studio dans l'autre sens : un projet construit au CLI ou à
    l'éditeur texte devient pleinement visible dans Studio à l'ouverture.
    """
    # Jobs : tout dossier jobs/<nom>/ contenant pipeline.yaml
    jobs_root = project_path / "jobs"
    if jobs_root.exists():
        for d in sorted(jobs_root.iterdir()):
            if d.is_dir() and (d / "pipeline.yaml").exists():
                _register_job_in_manifest(project_path, d.name, f"jobs/{d.name}")

    # Workflows : tout fichier workflows/*.yaml sans méta Studio existante
    wf_root  = project_path / "workflows"
    meta_dir = project_path / ".hydra" / "workflows"
    known_files: set = set()
    if meta_dir.exists():
        for f in meta_dir.glob("*.json"):
            try:
                known_files.add(json.loads(f.read_text(encoding="utf-8")).get("path"))
            except Exception:
                pass
    if not wf_root.exists():
        return
    for f in sorted(list(wf_root.glob("*.yaml")) + list(wf_root.glob("*.yml"))):
        if str(f) in known_files:
            continue
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            wf_section = doc.get("workflow", {}) if isinstance(doc, dict) else {}
        except Exception:
            wf_section = {}
        trigger = wf_section.get("trigger") or {}
        wf_id = str(uuid.uuid4())[:8]
        wf = WorkflowResponse(
            id=wf_id,
            name=wf_section.get("name", f.stem),
            project_id=project_id,
            description=wf_section.get("description") or None,
            trigger_type=trigger.get("type", "manual"),
            cron=trigger.get("cron"),
            published=False,
            path=str(f),
            layout=None,
        )
        meta_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            _wf_meta_new(project_path, wf_id),
            wf.model_dump_json(indent=2, exclude={"yaml_content"}))
        _register_workflow_in_manifest(project_path, wf_id, wf.name, f"workflows/{f.name}")


# ---------------------------------------------------------------------------
# Workflows
# 1 workflow = 1 fichier workflows/<slug>.yaml + méta .hydra/workflows/<id>.json
# Legacy : workflows/<id>/workflow.yaml + .hydra_workflow.json (lecture seule)
# ---------------------------------------------------------------------------

def _wf_meta_new(project_path: Path, workflow_id: str) -> Path:
    return project_path / ".hydra" / "workflows" / f"{workflow_id}.json"


def _wf_dir_legacy(project_path: Path, workflow_id: str) -> Path:
    return project_path / "workflows" / workflow_id


def _wf_meta_legacy(project_path: Path, workflow_id: str) -> Path:
    return _wf_dir_legacy(project_path, workflow_id) / ".hydra_workflow.json"


def _read_wf_meta(project_path: Path, workflow_id: str) -> Optional[dict]:
    """Méta workflow : nouveau format d'abord, legacy ensuite."""
    for meta in (_wf_meta_new(project_path, workflow_id), _wf_meta_legacy(project_path, workflow_id)):
        if meta.exists():
            try:
                return json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def _is_legacy_wf(project_path: Path, workflow_id: str) -> bool:
    return _wf_meta_legacy(project_path, workflow_id).exists() and not _wf_meta_new(project_path, workflow_id).exists()


def _wf_yaml_file(project_path: Path, workflow_id: str) -> Optional[Path]:
    """Chemin du fichier workflow.yaml, quel que soit le format."""
    if _is_legacy_wf(project_path, workflow_id):
        return _wf_dir_legacy(project_path, workflow_id) / "workflow.yaml"
    data = _read_wf_meta(project_path, workflow_id)
    if data and data.get("path"):
        p = Path(data["path"])
        if p.is_dir():          # méta legacy migrée à la main
            return p / "workflow.yaml"
        return p
    return None


def list_workflows(project_id: str) -> List[WorkflowResponse]:
    project_path = _resolve_project_path(project_id)
    result: List[WorkflowResponse] = []
    seen: set = set()

    # Nouveau format : méta dans .hydra/workflows/
    meta_dir = project_path / ".hydra" / "workflows"
    if meta_dir.exists():
        for f in sorted(meta_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(WorkflowResponse(**data))
                seen.add(data.get("id"))
            except Exception:
                pass

    # Legacy : sous-dossiers de workflows/
    wf_root = project_path / "workflows"
    if wf_root.exists():
        for d in sorted(wf_root.iterdir()):
            meta = d / ".hydra_workflow.json"
            if d.is_dir() and meta.exists():
                try:
                    data = json.loads(meta.read_text(encoding="utf-8"))
                    if data.get("id") not in seen:
                        result.append(WorkflowResponse(**data))
                except Exception:
                    pass
    return result


def get_workflow(project_id: str, workflow_id: str) -> Optional[WorkflowResponse]:
    project_path = _resolve_project_path(project_id)
    data = _read_wf_meta(project_path, workflow_id)
    if not data:
        return None
    wf = WorkflowResponse(**data)
    f = _wf_yaml_file(project_path, workflow_id)
    if f and f.exists():
        try:
            wf.yaml_content = f.read_text(encoding="utf-8")
        except Exception:
            pass
    return wf


def _save_wf_meta(project_path: Path, wf: WorkflowResponse) -> None:
    payload = wf.model_dump_json(indent=2, exclude={"yaml_content"})
    if _is_legacy_wf(project_path, wf.id):
        atomic_write_text(_wf_meta_legacy(project_path, wf.id), payload)
    else:
        meta = _wf_meta_new(project_path, wf.id)
        meta.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(meta, payload)


def create_workflow(
    project_id: str,
    name: str,
    description: Optional[str],
    trigger_type: str,
    cron: Optional[str],
) -> WorkflowResponse:
    project_path = _resolve_project_path(project_id)
    wf_id = str(uuid.uuid4())[:8]

    wf_root = project_path / "workflows"
    wf_root.mkdir(parents=True, exist_ok=True)

    # 1 workflow = 1 fichier — collision de nom → suffixe id
    slug = _slug(name)
    wf_file = wf_root / f"{slug}.yaml"
    if wf_file.exists():
        wf_file = wf_root / f"{slug}_{wf_id}.yaml"

    manifest = {
        "version": "1.0",
        "workflow": {
            "name": name,
            "description": description or "",
            "trigger": {"type": trigger_type, **({"cron": cron} if cron else {})},
            "steps": [],
        },
    }
    atomic_write_text(
        wf_file,
        yaml.dump(manifest, default_flow_style=False, allow_unicode=True, sort_keys=False),
    )

    wf = WorkflowResponse(
        id=wf_id,
        name=name,
        project_id=project_id,
        description=description,
        trigger_type=trigger_type,
        cron=cron,
        published=False,
        path=str(wf_file),
        layout=None,
    )
    _save_wf_meta(project_path, wf)
    _register_workflow_in_manifest(project_path, wf_id, name, f"workflows/{wf_file.name}")
    return wf


def _materialize_jobs(project_path: Path, jobs: List[dict]) -> None:
    """Écrit chaque job comme un vrai dossier jobs/<nom>/ avec les 4 YAML.

    C'est CE qui garantit la symétrie CLI ↔ Studio : un job créé dans le
    canvas existe physiquement sur disk et reste exécutable par hdrctl.
    """
    for job in jobs:
        name = _slug(job.get("name", "job"))
        job_dir = project_path / "jobs" / name
        job_dir.mkdir(parents=True, exist_ok=True)
        for fname, key in (
            ("sources.yaml", "sources"),
            ("transformations.yaml", "transformations"),
            ("destinations.yaml", "destinations"),
            ("pipeline.yaml", "pipeline"),
        ):
            content = job.get(key) or ""
            atomic_write_text(job_dir / fname, content)
        _register_job_in_manifest(project_path, name, f"jobs/{name}")


def update_workflow(project_id: str, workflow_id: str, patch: dict) -> Optional[WorkflowResponse]:
    project_path = _resolve_project_path(project_id)
    wf = get_workflow(project_id, workflow_id)
    if not wf:
        return None

    # Champs hors modèle WorkflowResponse
    yaml_content = patch.pop("yaml_content", None)
    jobs = patch.pop("jobs", None)

    data = wf.model_dump()
    data.update({k: v for k, v in patch.items() if v is not None})
    wf_updated = WorkflowResponse(**data)
    _save_wf_meta(project_path, wf_updated)

    # Matérialiser les jobs sur disk (jobs/<nom>/*.yaml)
    if jobs:
        _materialize_jobs(project_path, jobs)

    # Persister le workflow.yaml sérialisé depuis le canvas
    if yaml_content:
        wf_file = _wf_yaml_file(project_path, workflow_id)
        if wf_file:
            wf_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(wf_file, yaml_content)

    # Changement de trigger SANS re-sérialisation du canvas (ex. depuis la carte
    # projet) : on patche le bloc `trigger` du fichier YAML, qui est la source de
    # vérité lue par le runner / le scheduler / le webhook. Sinon la métadonnée et
    # le YAML divergent et le scheduler ignore le nouveau trigger.
    elif "trigger_type" in patch or "cron" in patch:
        wf_file = _wf_yaml_file(project_path, workflow_id)
        if wf_file and wf_file.exists():
            try:
                doc = yaml.safe_load(wf_file.read_text(encoding="utf-8")) or {}
                if not isinstance(doc, dict):
                    doc = {}
                wf_sec = doc.get("workflow")
                if not isinstance(wf_sec, dict):
                    wf_sec = {}
                    doc["workflow"] = wf_sec
                trig = {"type": wf_updated.trigger_type}
                if wf_updated.trigger_type == "schedule" and wf_updated.cron:
                    trig["cron"] = wf_updated.cron
                wf_sec["trigger"] = trig
                atomic_write_text(
                    wf_file,
                    yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False),
                )
            except Exception:
                pass

    return wf_updated


def publish_workflow(project_id: str, workflow_id: str) -> Optional[WorkflowResponse]:
    return update_workflow(project_id, workflow_id, {"published": True})


def delete_workflow(project_id: str, workflow_id: str) -> bool:
    project_path = _resolve_project_path(project_id)

    if _is_legacy_wf(project_path, workflow_id):
        wf_dir = _wf_dir_legacy(project_path, workflow_id)
        if not wf_dir.exists():
            return False
        import shutil
        shutil.rmtree(wf_dir)
        return True

    meta = _wf_meta_new(project_path, workflow_id)
    if not meta.exists():
        return False
    wf_file = _wf_yaml_file(project_path, workflow_id)
    if wf_file and wf_file.exists():
        wf_file.unlink()
    meta.unlink()
    _unregister_workflow_in_manifest(project_path, workflow_id)
    return True


# ---------------------------------------------------------------------------
# Runs (en mémoire)
# ---------------------------------------------------------------------------

def save_run(run: RunResponse) -> None:
    _runs[run.run_id] = run


def get_run(run_id: str) -> Optional[RunResponse]:
    return _runs.get(run_id)


def list_runs(workflow_name: Optional[str] = None) -> List[RunResponse]:
    runs = list(_runs.values())
    if workflow_name:
        runs = [r for r in runs if r.workflow_name == workflow_name]
    return sorted(runs, key=lambda r: r.started_at, reverse=True)


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

def _env_file(project_id: str, env_name: str) -> Path:
    return _resolve_project_path(project_id) / f".env.{env_name}"


def list_environments(project_id: str) -> List[EnvironmentResponse]:
    path = _resolve_project_path(project_id)
    if not path.exists():
        return []
    envs = []
    for f in path.glob(".env.*"):
        env_name = f.name[5:]  # strip ".env."
        vars_dict = _parse_dotenv(f)
        envs.append(EnvironmentResponse(
            id=f"{project_id}_{env_name}",
            name=env_name,
            project_id=project_id,
            vars=vars_dict,
        ))
    return envs


def get_environment(project_id: str, env_name: str) -> Optional[EnvironmentResponse]:
    f = _env_file(project_id, env_name)
    if not f.exists():
        return None
    return EnvironmentResponse(
        id=f"{project_id}_{env_name}",
        name=env_name,
        project_id=project_id,
        vars=_parse_dotenv(f),
    )


def create_environment(project_id: str, name: str, vars: dict) -> EnvironmentResponse:
    f = _env_file(project_id, name)
    atomic_write_text(f, _dump_dotenv(vars))
    return EnvironmentResponse(id=f"{project_id}_{name}", name=name, project_id=project_id, vars=vars)


def update_environment(project_id: str, env_name: str, vars: dict) -> Optional[EnvironmentResponse]:
    f = _env_file(project_id, env_name)
    if not f.exists():
        return None
    existing = _parse_dotenv(f)
    existing.update(vars)
    atomic_write_text(f, _dump_dotenv(existing))
    return EnvironmentResponse(id=f"{project_id}_{env_name}", name=env_name, project_id=project_id, vars=existing)


def delete_environment(project_id: str, env_name: str) -> bool:
    f = _env_file(project_id, env_name)
    if not f.exists():
        return False
    f.unlink()
    return True


def _parse_dotenv(path: Path) -> dict:
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip()
    return result


def _dump_dotenv(vars: dict) -> str:
    return "\n".join(f"{k}={v}" for k, v in vars.items()) + "\n"
