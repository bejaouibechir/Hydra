"""
Sous-package internal.connector.

Regroupe tous les connecteurs de données.
"""

from .interface import Connector
from .csv_connector import CSVConnector
from .json_connector import JSONConnector
from .mysql_mariadb_connector import MySQLMariaDBConnector
from .parquet_connector import ParquetConnector
from .postgresql_connector import PostgreSQLConnector
from .web_api_connector import WebAPIConnector

__all__ = [
    "Connector",
    "CSVConnector",
    "JSONConnector",
    "MySQLMariaDBConnector",
    "ParquetConnector",
    "PostgreSQLConnector",
    "WebAPIConnector",
]