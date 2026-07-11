"""
MongoDB document normalizer.

Transforms MongoDB documents into flat tabular format suitable for Hydra pipelines.
"""

from typing import Dict, List, Any, Optional, Iterator
import logging

from internal.schema import (
    SchemaDescriptor,
    FieldDescriptor,
    FieldType,
    ArrayHandling
)
from internal.schema.policies import FieldPolicy

logger = logging.getLogger(__name__)


class DocumentNormalizer:
    """
    Normalizes MongoDB documents to tabular format.
    
    Handles:
    - Nested field extraction (customer.name -> customer_name)
    - Array flattening/exploding
    - Type coercion
    - Missing field handling
    - Schema drift tolerance
    
    Examples:
        normalizer = DocumentNormalizer(schema)
        
        doc = {
            "order_id": "ORD-001",
            "customer": {"name": "Alice", "email": "alice@example.com"},
            "total": 99.99
        }
        
        flat = normalizer.normalize_document(doc)
        # Result: {"order_id": "ORD-001", "customer_name": "Alice", ...}
    """
    
    def __init__(
        self,
        schema: SchemaDescriptor,
        field_policy: Optional[FieldPolicy] = None
    ):
        """
        Initialize normalizer.
        
        Args:
            schema: Schema descriptor
            field_policy: Policy for handling field issues
        """
        self.schema = schema
        self.field_policy = field_policy or FieldPolicy()
    
    def normalize_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a single MongoDB document to flat structure.
        
        Args:
            document: MongoDB document
            
        Returns:
            Flat dictionary matching schema
        """
        normalized = {}
        
        for field in self.schema.fields:
            # Skip array fields (handled separately)
            if field.is_array() and field.array_handling == ArrayHandling.EXPLODE:
                continue
            
            value = self._extract_field(document, field)
            normalized[field.name] = value
        
        return normalized
    
    def normalize_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize a batch of documents.
        
        Args:
            documents: List of MongoDB documents
            
        Returns:
            List of normalized flat dictionaries
        """
        return [self.normalize_document(doc) for doc in documents]
    
    def normalize_with_explode(
        self,
        document: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Normalize document and explode array fields into multiple rows.
        
        Args:
            document: MongoDB document
            
        Returns:
            List of normalized records (one per array element)
        """
        # Find array fields to explode
        explode_fields = [
            f for f in self.schema.fields
            if f.is_array() and f.array_handling == ArrayHandling.EXPLODE
        ]
        
        if not explode_fields:
            # No arrays to explode, return single record
            return [self.normalize_document(document)]
        
        # For now, handle single array field
        # TODO: Handle multiple array fields (cartesian product)
        if len(explode_fields) > 1:
            logger.warning(f"Multiple array explode not fully supported, using first: {explode_fields[0].name}")
        
        array_field = explode_fields[0]
        array_values = self._extract_field(document, array_field)
        
        if not isinstance(array_values, (list, tuple)) or not array_values:
            # No array or empty, return single record
            return [self.normalize_document(document)]
        
        # Create one record per array element
        records = []
        base_record = self._normalize_without_arrays(document)
        
        for array_item in array_values:
            record = base_record.copy()
            
            # Add array item data
            if isinstance(array_item, dict):
                # Array of objects - flatten
                for key, value in array_item.items():
                    field_name = f"{array_field.name}_{key}"
                    record[field_name] = value
            else:
                # Array of primitives
                record[array_field.name] = array_item
            
            records.append(record)
        
        return records
    
    def _normalize_without_arrays(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to normalize document excluding array fields."""
        normalized = {}
        
        for field in self.schema.fields:
            if field.is_array() and field.array_handling == ArrayHandling.EXPLODE:
                continue
            
            value = self._extract_field(document, field)
            normalized[field.name] = value
        
        return normalized
    
    def _extract_field(
        self,
        document: Dict[str, Any],
        field: FieldDescriptor
    ) -> Any:
        """
        Extract field value from document using path.
        
        Args:
            document: Source document
            field: Field descriptor with path
            
        Returns:
            Extracted value or default/None
        """
        path = field.path or field.name
        
        # Handle nested paths (e.g., "customer.name")
        if "." in path:
            value = self._extract_nested(document, path)
        # Handle array paths (e.g., "items[]")
        elif path.endswith("[]"):
            clean_path = path.rstrip("[]")
            value = document.get(clean_path)
        else:
            # Simple field
            value = document.get(path)
        
        # Handle missing field
        if value is None:
            return self.field_policy.handle_missing(field.name, field.default)
        
        # Handle type mismatch
        if not self._validate_type(value, field.type):
            return self.field_policy.handle_type_mismatch(
                field.name,
                field.type.value,
                value
            )
        
        # Handle array conversion
        if field.type == FieldType.ARRAY and field.array_handling == ArrayHandling.JSON:
            import json
            return json.dumps(value)
        
        return value
    
    def _extract_nested(self, document: Dict[str, Any], path: str) -> Any:
        """
        Extract value from nested path.
        
        Args:
            document: Source document
            path: Dot-notation path (e.g., "customer.address.city")
            
        Returns:
            Value or None if path doesn't exist
        """
        parts = path.split(".")
        current = document
        
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return None
            else:
                return None
        
        return current
    
    def _validate_type(self, value: Any, expected_type: FieldType) -> bool:
        """
        Check if value matches expected type.
        
        Args:
            value: Value to check
            expected_type: Expected FieldType
            
        Returns:
            True if type matches
        """
        if value is None:
            return True
        
        type_checks = {
            FieldType.STRING: lambda v: isinstance(v, str),
            FieldType.INTEGER: lambda v: isinstance(v, int) and not isinstance(v, bool),
            FieldType.FLOAT: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            FieldType.DECIMAL: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            FieldType.BOOLEAN: lambda v: isinstance(v, bool),
            FieldType.ARRAY: lambda v: isinstance(v, (list, tuple)),
            FieldType.OBJECT: lambda v: isinstance(v, dict),
            FieldType.JSON: lambda v: True,
        }
        
        checker = type_checks.get(expected_type)
        if not checker:
            return True
        
        return checker(value)
    
    def normalize_stream(
        self,
        documents: Iterator[Dict[str, Any]],
        explode_arrays: bool = False
    ) -> Iterator[Dict[str, Any]]:
        """
        Normalize documents in streaming fashion.
        
        Args:
            documents: Iterator of MongoDB documents
            explode_arrays: Whether to explode array fields
            
        Yields:
            Normalized flat dictionaries
        """
        for doc in documents:
            if explode_arrays:
                for record in self.normalize_with_explode(doc):
                    yield record
            else:
                yield self.normalize_document(doc)
    
    def get_output_columns(self) -> List[str]:
        """
        Get list of output column names.
        
        Returns:
            List of column names in output
        """
        columns = []
        
        for field in self.schema.fields:
            if field.is_array() and field.array_handling == ArrayHandling.EXPLODE:
                # Array fields will be expanded dynamically
                # We can't know column names without seeing data
                columns.append(f"{field.name}_*")
            else:
                columns.append(field.name)
        
        return columns
    
    def estimate_row_count(
        self,
        document_count: int,
        sample_documents: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """
        Estimate output row count when arrays are exploded.
        
        Args:
            document_count: Number of input documents
            sample_documents: Sample to estimate array sizes
            
        Returns:
            Estimated output row count
        """
        explode_fields = [
            f for f in self.schema.fields
            if f.is_array() and f.array_handling == ArrayHandling.EXPLODE
        ]
        
        if not explode_fields:
            return document_count
        
        if not sample_documents:
            # No sample, assume arrays have 3 elements on average
            return document_count * 3
        
        # Calculate average array size from sample
        array_field = explode_fields[0]
        array_sizes = []
        
        for doc in sample_documents:
            value = self._extract_field(doc, array_field)
            if isinstance(value, (list, tuple)):
                array_sizes.append(len(value))
        
        if array_sizes:
            avg_size = sum(array_sizes) / len(array_sizes)
            return int(document_count * avg_size)
        
        return document_count