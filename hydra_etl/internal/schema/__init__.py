"""
Schema management layer for atypical data sources.

This module provides schema definition, validation, and drift detection
capabilities for sources that lack fixed schemas (MongoDB, JSON, APIs, etc.).
"""

from .descriptor import (
    SchemaDescriptor,
    FieldDescriptor,
    FieldType,
    ArrayHandling,
    SchemaMode
)
from .policies import (
    DriftPolicy,
    ValidationPolicy,
    FieldPolicy,
    PolicyFactory
)
from .validator import SchemaValidator, ValidationResult

__all__ = [
    # Descriptor
    'SchemaDescriptor',
    'FieldDescriptor',
    'FieldType',
    'ArrayHandling',
    'SchemaMode',
    # Policies
    'DriftPolicy',
    'ValidationPolicy',
    'FieldPolicy',
    'PolicyFactory',
    # Validator
    'SchemaValidator',
    'ValidationResult',
]