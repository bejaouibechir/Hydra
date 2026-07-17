"""
Sous-package internal.connector.

Regroupe tous les connecteurs de données.
"""

from .interface import Connector
from .csv_connector import CSVConnector
from .json_connector import JSONConnector
from .mysql_mariadb_connector import MySQLMariaDBConnector
from .postgresql_connector import PostgreSQLConnector

# WebAPIConnector — optionnel (depend de jsonpath_ng)
try:
    from .web_api_connector_v2 import WebAPIConnector
    _WEBAPI_AVAILABLE = True
except ImportError:
    WebAPIConnector = None  # type: ignore[assignment,misc]
    _WEBAPI_AVAILABLE = False

# ParquetConnector — optionnel (depend de pyarrow)
try:
    from .parquet_connector import ParquetConnector
    _PARQUET_AVAILABLE = True
except ImportError:
    ParquetConnector = None  # type: ignore[assignment,misc]
    _PARQUET_AVAILABLE = False

__all__ = [
    "Connector",
    "CSVConnector",
    "JSONConnector",
    "MySQLMariaDBConnector",
    "ParquetConnector",
    "PostgreSQLConnector",
    "WebAPIConnector",
]
