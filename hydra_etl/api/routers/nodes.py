"""
api/routers/nodes.py — Catalogue des nœuds disponibles (connecteurs + transformations).

Introspection dynamique du registry Hydra : ce qui est installé et disponible
dans l'environnement Python courant.
"""
from typing import List, Optional
from fastapi import APIRouter, Query

from hydra_etl.api.models import NodeInfo

router = APIRouter()


def _build_catalogue() -> List[NodeInfo]:
    """Construit le catalogue dynamiquement depuis les connecteurs disponibles."""
    nodes = []

    # --- Sources / Destinations (connecteurs) ---
    connector_defs = [
        ("csv",        "CSV",              "Lire/écrire des fichiers CSV"),
        ("json",       "JSON",             "Lire/écrire des fichiers JSON"),
        ("mysql",      "MySQL / MariaDB",  "Connecteur MySQL et MariaDB"),
        ("postgresql", "PostgreSQL",       "Connecteur PostgreSQL"),
        ("mongodb",    "MongoDB",          "Connecteur MongoDB"),
        ("web_api",    "Web API",          "Appels HTTP GET/POST (REST)"),
    ]

    for cid, cname, cdesc in connector_defs:
        nodes.append(NodeInfo(
            id=cid,
            name=cname,
            category="source",
            description=cdesc,
        ))
        nodes.append(NodeInfo(
            id=f"{cid}_dest",
            name=f"{cname} (destination)",
            category="destination",
            description=cdesc,
        ))

    # Parquet — optionnel selon pyarrow
    try:
        import pyarrow  # noqa: F401
        nodes.append(NodeInfo(id="parquet",      name="Parquet", category="source",      description="Fichiers Parquet (Apache Arrow)"))
        nodes.append(NodeInfo(id="parquet_dest", name="Parquet (destination)", category="destination", description="Fichiers Parquet (Apache Arrow)"))
    except ImportError:
        pass

    # --- Transformations ---
    transform_defs = [
        ("filter",      "Filter",      "Filtre les lignes selon une condition"),
        ("select",      "Select",      "Sélectionne des colonnes"),
        ("rename",      "Rename",      "Renomme des colonnes"),
        ("cast",        "Cast",        "Change le type d'une colonne"),
        ("aggregate",   "Aggregate",   "Agrège les données (groupby)"),
        ("sort",        "Sort",        "Trie les lignes"),
        ("deduplicate", "Deduplicate", "Supprime les doublons"),
        ("derive",      "Derive",      "Crée une colonne calculée"),
        ("pivot",       "Pivot",       "Pivote le tableau"),
        ("unpivot",     "Unpivot",     "Dépivote le tableau"),
        ("clean",       "Clean",       "Nettoie les données (trim, lowercase...)"),
        ("fill_null",   "Fill Null",   "Remplace les valeurs nulles"),
        ("index",       "Index",       "Réindexe les lignes"),
    ]
    for tid, tname, tdesc in transform_defs:
        nodes.append(NodeInfo(id=tid, name=tname, category="transformation", description=tdesc))

    # --- Actions (workflow-level) ---
    action_defs = [
        ("webhook",  "Webhook",       "Appel HTTP en fin de step"),
        ("log",      "Log",           "Écriture dans les logs"),
        ("email",    "Email",         "Envoi d'un email de notification"),
        ("slack",    "Slack",         "Message Slack"),
    ]
    for aid, aname, adesc in action_defs:
        nodes.append(NodeInfo(id=aid, name=aname, category="action", description=adesc))

    return nodes


_CATALOGUE = _build_catalogue()


@router.get("", response_model=List[NodeInfo])
def list_nodes(category: Optional[str] = Query(None, description="Filtrer par catégorie: source|destination|transformation|action")):
    """Retourne le catalogue des nœuds disponibles."""
    if category:
        return [n for n in _CATALOGUE if n.category == category]
    return _CATALOGUE


@router.get("/{node_id}", response_model=NodeInfo)
def get_node(node_id: str):
    from fastapi import HTTPException
    node = next((n for n in _CATALOGUE if n.id == node_id), None)
    if not node:
        raise HTTPException(404, detail=f"Node '{node_id}' not found")
    return node
