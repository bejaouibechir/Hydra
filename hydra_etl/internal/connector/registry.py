"""
Connector registry - Factory pattern pour instancier les connecteurs.

Extensibilite maximale : +1 ligne = nouveau type de connecteur.
"""

from typing import Dict, Callable, Any

from .interface import Connector
from .csv_connector import CSVConnector
from .json_connector import JSONConnector
from .mysql_mariadb_connector import MySQLMariaDBConnector
from .postgresql_connector import PostgreSQLConnector

# Import MongoDB connector -- optionnel (dependance pymongo)
try:
    from hydra_etl.plugins.connectors.mongodb import MongoDBConnector as _MongoDBConnector
    _MONGODB_AVAILABLE = True
except Exception:
    _MongoDBConnector = None  # type: ignore[assignment,misc]
    _MONGODB_AVAILABLE = False

# Import Parquet connector -- optionnel (dependance pyarrow)
try:
    from hydra_etl.internal.connector.parquet_connector import ParquetConnector as _ParquetConnector
    _PARQUET_AVAILABLE = True
except Exception:
    _ParquetConnector = None  # type: ignore[assignment,misc]
    _PARQUET_AVAILABLE = False

# Import Web API connector -- optionnel
try:
    from hydra_etl.internal.connector.web_api_connector_v2 import WebAPIConnector as _WebAPIConnector
    _WEBAPI_AVAILABLE = True
except Exception:
    _WebAPIConnector = None  # type: ignore[assignment,misc]
    _WEBAPI_AVAILABLE = False

# ============================================================
# Type Alias
# ============================================================

ConnectorFactory = Callable[[str, Dict[str, Any]], Connector]


# ============================================================
# Factories specifiques
# ============================================================

def _build_csv_connector(name: str, config: Dict[str, Any]) -> "CSVConnector":
    """Factory pour CSVConnector (necessite job_dir)."""
    if "job_dir" not in config:
        raise ValueError(
            f"CSVConnector '{name}' requires 'job_dir' in config"
        )
    return CSVConnector(
        name=name,
        job_dir=config["job_dir"],
        config=config
    )


def _build_json_connector(name: str, config: Dict[str, Any]) -> "JSONConnector":
    """Factory pour JSONConnector (injecte job_dir pour resolution des chemins relatifs)."""
    if "job_dir" not in config:
        raise ValueError(
            f"JSONConnector '{name}' requires 'job_dir' in config"
        )
    return JSONConnector(name=name, config=config)


def _build_db_connector(connector_class: type) -> ConnectorFactory:
    """Factory generique pour connecteurs base de donnees."""
    def factory(name: str, config: Dict[str, Any]) -> Connector:
        return connector_class(name=name, config=config)
    return factory


# ============================================================
# Registry : mapping type -> factory
# ============================================================

CONNECTOR_REGISTRY: Dict[str, ConnectorFactory] = {
    # Fichiers
    "csv": _build_csv_connector,
    "json": _build_json_connector,

    # SQL Databases
    "mysql": _build_db_connector(MySQLMariaDBConnector),
    "mariadb": _build_db_connector(MySQLMariaDBConnector),
    "postgresql": _build_db_connector(PostgreSQLConnector),
    "postgres": _build_db_connector(PostgreSQLConnector),
}

# Enregistrement conditionnel des connecteurs a dependances optionnelles
if _MONGODB_AVAILABLE and _MongoDBConnector is not None:
    CONNECTOR_REGISTRY["mongodb"] = _build_db_connector(_MongoDBConnector)

if _PARQUET_AVAILABLE and _ParquetConnector is not None:
    CONNECTOR_REGISTRY["parquet"] = _build_db_connector(_ParquetConnector)

if _WEBAPI_AVAILABLE and _WebAPIConnector is not None:
    CONNECTOR_REGISTRY["web_api"] = _build_db_connector(_WebAPIConnector)


# ============================================================
# Build connector : point d'entree principal
# ============================================================

def build_connector(*, name: str, config: Dict[str, Any]) -> Connector:
    """
    Instancie un connecteur via factory pattern.

    Args:
        name: Nom du connecteur (ex: 'src_orders')
        config: Configuration complete incluant 'type'

    Returns:
        Instance du connecteur approprie

    Raises:
        ValueError: Si type manquant, inconnu, ou factory echoue
    """
    ctype = config.get("type")
    if not isinstance(ctype, str) or not ctype.strip():
        raise ValueError(
            f"Connector '{name}': field 'type' is missing or invalid in config."
        )
    ctype = ctype.strip().lower()

    factory = CONNECTOR_REGISTRY.get(ctype)
    if factory is None:
        supported = ", ".join(sorted(CONNECTOR_REGISTRY.keys()))
        raise ValueError(
            f"Connector '{name}': unknown type '{ctype}'. "
            f"Supported types: {supported}"
        )

    try:
        return factory(name, config)
    except Exception as e:
        raise ValueError(
            f"Connector '{name}': factory failed for type '{ctype}': {e}"
        ) from e
