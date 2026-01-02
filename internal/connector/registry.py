"""
Registry des connecteurs disponibles - Pattern Factory.

Changements v1.1 (Sprint 1):
- Passage de Dict[str, Type] à Dict[str, Factory]
- Élimination dispatch hardcodé (if ctype == "csv")
- Chaque factory encapsule sa logique d'instanciation
- Ajout nouveau connecteur = +1 ligne registry
"""

from typing import Dict, Type, Any, Callable, Protocol
from internal.connector.interface import Connector
from internal.connector.csv_connector import CSVConnector
from internal.connector.mysql_mariadb_connector import MySQLMariaDBConnector


# ============================================================
# Protocol Factory : signature commune pour toutes les factories
# ============================================================

class ConnectorFactory(Protocol):
    """
    Protocol pour factories de connecteurs.
    
    Chaque factory sait comment instancier son type de connecteur
    avec les paramètres spécifiques dont il a besoin.
    """
    def __call__(self, name: str, config: Dict[str, Any]) -> Connector:
        """
        Instancie un connecteur.
        
        Args:
            name: Nom du connecteur (ex: 'src_orders')
            config: Configuration complète du connecteur
        
        Returns:
            Instance du connecteur
        
        Raises:
            ValueError: Si configuration invalide
        """
        ...


# ============================================================
# Factories concrètes : une factory par type de connecteur
# ============================================================

def _build_csv_connector(name: str, config: Dict[str, Any]) -> Connector:
    """
    Factory pour CSVConnector.
    
    CSV nécessite 'job_dir' pour résoudre les chemins relatifs.
    L'executor doit l'injecter via config['job_dir'].
    
    Args:
        name: Nom du connecteur
        config: Configuration avec 'job_dir' obligatoire
    
    Returns:
        Instance CSVConnector
    
    Raises:
        ValueError: Si job_dir manquant
    
    Exemple config:
        {
            "type": "csv",
            "job_dir": "/path/to/job",  # Injecté par executor
            "extract": {...}
        }
    """
    job_dir = config.get("job_dir")
    if job_dir is None:
        raise ValueError(
            f"CSV Connector '{name}' requires 'job_dir' in config. "
            f"Executor must inject it via config['job_dir']."
        )
    return CSVConnector(name=name, config=config, job_dir=job_dir)


def _build_db_connector(connector_class: Type[Connector]) -> ConnectorFactory:
    """
    Factory générique pour connecteurs DB (signature standard).
    
    Tous les connecteurs SQL (MySQL, PostgreSQL, etc.) utilisent
    la même signature : __init__(name, config).
    
    Args:
        connector_class: Classe du connecteur (ex: MySQLMariaDBConnector)
    
    Returns:
        Factory function pour ce connecteur
    
    Exemple:
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
    
    # Futurs connecteurs (exemples commentés):
    # "postgresql": _build_db_connector(PostgreSQLConnector),
    # "mongodb": _build_mongo_connector,  # Factory custom si besoin
    # "kafka": _build_kafka_connector,    # Factory custom si besoin
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
            f"Connector '{name}' (type={ctype}): "
            f"factory failed with {type(e).__name__}: {e}"
        ) from e