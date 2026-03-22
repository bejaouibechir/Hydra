"""
Connector registry - Factory pattern pour instancier les connecteurs.

Extensibilité maximale : +1 ligne = nouveau type de connecteur.
"""

from typing import Dict, Callable, Any

from .interface import Connector
from .csv_connector import CSVConnector
from .mysql_mariadb_connector import MySQLMariaDBConnector

# Import MongoDB connector
from plugins.connectors.mongodb import MongoDBConnector

#Import Parquet connector
from internal.connector.parquet_connector import ParquetConnector

# ============================================================
# Type Alias
# ============================================================

ConnectorFactory = Callable[[str, Dict[str, Any]], Connector]
"""
Signature d'une factory de connecteur.

Args:
    name: Nom du connecteur
    config: Configuration complète

Returns:
    Instance de Connector
"""


# ============================================================
# Factories spécifiques
# ============================================================

def _build_csv_connector(name: str, config: Dict[str, Any]) -> CSVConnector:
    """
    Factory pour CSVConnector (nécessite job_dir).
    
    Args:
        name: Nom du connecteur
        config: Configuration incluant job_dir
    
    Returns:
        Instance de CSVConnector
    
    Raises:
        ValueError: Si job_dir manquant
    """
    # Validation spécifique CSV
    if "job_dir" not in config:
        raise ValueError(
            f"CSVConnector '{name}' requires 'job_dir' in config"
        )
    
    return CSVConnector(
        name=name,
        job_dir=config["job_dir"],
        config=config
    )


def _build_db_connector(connector_class: type) -> ConnectorFactory:
    """
    Factory générique pour connecteurs base de données.
    
    Génère une factory pour une classe de connecteur qui suit
    la signature standard (name, config).
    
    Args:
        connector_class: Classe du connecteur (ex: MySQLMariaDBConnector)
    
    Returns:
        Factory function pour ce type de connecteur
    
    Exemples:
        mysql_factory = _build_db_connector(MySQLMariaDBConnector)
        connector = mysql_factory("src_db", {"type": "mysql", ...})
    """
    def factory(name: str, config: Dict[str, Any]) -> Connector:
        return connector_class(name=name, config=config)
    return factory


# ============================================================
# Registry : mapping type → factory
# ============================================================

CONNECTOR_REGISTRY: Dict[str, ConnectorFactory] = {
    # Fichiers
    "csv": _build_csv_connector,
    
    # SQL Databases
    "mysql": _build_db_connector(MySQLMariaDBConnector),
    "mariadb": _build_db_connector(MySQLMariaDBConnector),
    
    # NoSQL Databases
    "mongodb": _build_db_connector(MongoDBConnector),
}


# ============================================================
# Build connector : point d'entrée principal
# ============================================================

def build_connector(*, name: str, config: Dict[str, Any]) -> Connector:
    """
    Instancie un connecteur via factory pattern.
    
    Args:
        name: Nom du connecteur (ex: 'src_orders')
        config: Configuration complète incluant 'type'
    
    Returns:
        Instance du connecteur approprié
    
    Raises:
        ValueError: Si type manquant, inconnu, ou factory échoue
    
    Exemples:
        >>> # CSV
        >>> build_connector(
        ...     name="src_csv",
        ...     config={"type": "csv", "job_dir": "/path"}
        ... )
        <CSVConnector(name='src_csv')>
        
        >>> # MySQL
        >>> build_connector(
        ...     name="src_db",
        ...     config={"type": "mysql", "connection": {...}}
        ... )
        <MySQLMariaDBConnector(name='src_db')>
        
        >>> # MongoDB
        >>> build_connector(
        ...     name="src_mongo",
        ...     config={"type": "mongodb", "connection": {...}}
        ... )
        <MongoDBConnector(name='src_mongo')>
    """
    # Validation type
    ctype = config.get("type")
    if not isinstance(ctype, str) or not ctype.strip():
        raise ValueError(
            f"Connector '{name}': field 'type' is missing or invalid in config."
        )
    ctype = ctype.strip().lower()
    
    # Récupération factory
    factory = CONNECTOR_REGISTRY.get(ctype)
    if factory is None:
        supported = ", ".join(sorted(CONNECTOR_REGISTRY.keys()))
        raise ValueError(
            f"Connector '{name}': unknown type '{ctype}'. "
            f"Supported types: {supported}"
        )
    
    # Délégation à la factory (chaque factory sait ce dont elle a besoin)
    try:
        return factory(name, config)
    except Exception as e:
        raise ValueError(
            f"Connector '{name}': factory failed for type '{ctype}': {e}"
        ) from e