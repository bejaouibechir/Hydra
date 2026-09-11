"""
MongoDB connector plugin for Hydra.

Handles MongoDB as an atypical data source with:
- Schema inference from sample documents
- Nested document flattening
- Array handling (explode/flatten)
- Schema drift detection and adaptation
"""

from .connector import MongoDBConnector

__all__ = ['MongoDBConnector']