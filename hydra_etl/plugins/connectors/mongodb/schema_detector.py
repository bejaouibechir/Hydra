"""
MongoDB schema detector.

Automatically infers schema from sample documents.
"""

from typing import Dict, List, Any, Set, Optional
from collections import Counter
import logging

from hydra_etl.internal.schema import (
    SchemaDescriptor,
    FieldDescriptor,
    FieldType,
    SchemaMode,
    ArrayHandling
)

logger = logging.getLogger(__name__)


class SchemaDetector:
    """
    Detects schema from MongoDB documents.
    
    Analyzes sample documents to infer:
    - Field names and types
    - Nested structures
    - Array fields
    - Required vs optional fields
    - Field coverage (presence percentage)
    
    Examples:
        detector = SchemaDetector()
        
        documents = [
            {"id": 1, "name": "Alice", "age": 30},
            {"id": 2, "name": "Bob", "age": 25},
        ]
        
        schema = detector.infer_schema(documents)
        print(f"Detected {len(schema.fields)} fields")
    """
    
    def __init__(self, sample_size: int = 100):
        """
        Initialize schema detector.
        
        Args:
            sample_size: Number of documents to sample for inference
        """
        self.sample_size = sample_size
    
    def infer_schema(
        self,
        documents: List[Dict[str, Any]],
        mode: SchemaMode = SchemaMode.INFER_STRICT,
        required_threshold: float = 0.95
    ) -> SchemaDescriptor:
        """
        Infer schema from sample documents.
        
        Args:
            documents: List of MongoDB documents
            mode: Schema mode
            required_threshold: Percentage threshold to mark field as required (0-1)
            
        Returns:
            Inferred SchemaDescriptor
        """
        if not documents:
            return SchemaDescriptor(mode=mode, fields=[])
        
        # Analyze all fields
        field_stats = self._analyze_fields(documents)
        
        # Create field descriptors
        fields = []
        total_docs = len(documents)
        
        for field_name, stats in field_stats.items():
            field_desc = self._create_field_descriptor(
                field_name=field_name,
                stats=stats,
                total_docs=total_docs,
                required_threshold=required_threshold
            )
            fields.append(field_desc)
        
        # Sort fields by coverage (most common first)
        fields.sort(key=lambda f: field_stats.get(f.path, {}).get("coverage", 0), reverse=True)
        
        schema = SchemaDescriptor(
            mode=mode,
            fields=fields,
            sample_size=len(documents)
        )
        
        logger.info(f"Inferred schema with {len(fields)} fields from {len(documents)} documents")
        
        return schema
    
    def _analyze_fields(self, documents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Analyze all fields across documents.
        
        Returns:
            Dictionary of field_name -> statistics
        """
        field_stats: Dict[str, Dict[str, Any]] = {}
        
        for doc in documents:
            # Flatten document to get all paths
            flat_doc = self._flatten_document(doc)
            
            for field_path, value in flat_doc.items():
                if field_path not in field_stats:
                    field_stats[field_path] = {
                        "types": Counter(),
                        "count": 0,
                        "null_count": 0,
                        "sample_values": [],
                        "is_nested": "." in field_path,
                        "is_array": False
                    }
                
                stats = field_stats[field_path]
                stats["count"] += 1
                
                if value is None:
                    stats["null_count"] += 1
                else:
                    # Track type
                    value_type = type(value).__name__
                    stats["types"][value_type] += 1
                    
                    # Check if array
                    if isinstance(value, (list, tuple)):
                        stats["is_array"] = True
                    
                    # Store sample values
                    if len(stats["sample_values"]) < 5:
                        stats["sample_values"].append(value)
        
        # Calculate coverage
        total_docs = len(documents)
        for stats in field_stats.values():
            stats["coverage"] = (stats["count"] / total_docs) * 100
        
        return field_stats
    
    def _flatten_document(
        self,
        doc: Dict[str, Any],
        parent_key: str = "",
        separator: str = "."
    ) -> Dict[str, Any]:
        """
        Flatten nested document to dot-notation paths.
        
        Args:
            doc: Document to flatten
            parent_key: Parent key for recursion
            separator: Separator for nested keys
            
        Returns:
            Flattened document with dot-notation keys
        """
        items = []
        
        for key, value in doc.items():
            new_key = f"{parent_key}{separator}{key}" if parent_key else key
            
            if isinstance(value, dict) and value:
                # Nested document - recurse
                items.extend(self._flatten_document(value, new_key, separator).items())
            elif isinstance(value, (list, tuple)) and value and isinstance(value[0], dict):
                # Array of documents - mark as array but don't expand
                items.append((f"{new_key}[]", value))
            else:
                # Simple value or empty container
                items.append((new_key, value))
        
        return dict(items)
    
    def _create_field_descriptor(
        self,
        field_name: str,
        stats: Dict[str, Any],
        total_docs: int,
        required_threshold: float
    ) -> FieldDescriptor:
        """
        Create FieldDescriptor from field statistics.
        
        Args:
            field_name: Field name/path
            stats: Field statistics
            total_docs: Total number of documents
            required_threshold: Threshold for marking as required
            
        Returns:
            FieldDescriptor
        """
        # Determine most common type
        if stats["types"]:
            most_common_type = stats["types"].most_common(1)[0][0]
            field_type = self._map_python_type_to_field_type(most_common_type)
        else:
            field_type = FieldType.STRING  # Default
        
        # Check if array
        is_array = stats.get("is_array", False)
        if is_array:
            field_type = FieldType.ARRAY
        
        # Determine if required
        coverage = stats["coverage"] / 100
        is_required = coverage >= required_threshold
        
        # Extract clean field name and path
        if stats["is_nested"]:
            # Nested field: customer.name -> name: customer.name
            path = field_name
            name = field_name.replace(".", "_")
        elif field_name.endswith("[]"):
            # Array field: items[] -> items
            path = field_name
            name = field_name.rstrip("[]")
        else:
            # Simple field
            path = field_name
            name = field_name
        
        # Handle array fields
        array_handling = None
        if is_array:
            array_handling = ArrayHandling.KEEP  # Default, can be overridden
        
        return FieldDescriptor(
            name=name,
            type=field_type,
            path=path,
            required=is_required,
            array_handling=array_handling,
            description=f"Coverage: {stats['coverage']:.1f}%, Types: {dict(stats['types'])}"
        )
    
    def _map_python_type_to_field_type(self, python_type: str) -> FieldType:
        """
        Map Python type name to FieldType.
        
        Args:
            python_type: Python type name (e.g., 'int', 'str')
            
        Returns:
            Corresponding FieldType
        """
        type_mapping = {
            "int": FieldType.INTEGER,
            "float": FieldType.FLOAT,
            "str": FieldType.STRING,
            "bool": FieldType.BOOLEAN,
            "list": FieldType.ARRAY,
            "tuple": FieldType.ARRAY,
            "dict": FieldType.OBJECT,
            "NoneType": FieldType.STRING,  # Default for None
        }
        
        return type_mapping.get(python_type, FieldType.STRING)
    
    def detect_schema_changes(
        self,
        old_schema: SchemaDescriptor,
        new_documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detect changes between existing schema and new documents.
        
        Args:
            old_schema: Existing schema
            new_documents: New sample documents
            
        Returns:
            Dictionary with changes:
            - added_fields: New fields not in old schema
            - removed_fields: Old schema fields not in new documents
            - type_changes: Fields with different types
        """
        new_schema = self.infer_schema(new_documents)
        
        old_fields = {f.name for f in old_schema.fields}
        new_fields = {f.name for f in new_schema.fields}
        
        added = new_fields - old_fields
        removed = old_fields - new_fields
        
        # Check type changes
        type_changes = []
        for old_field in old_schema.fields:
            new_field = new_schema.get_field(old_field.name)
            if new_field and new_field.type != old_field.type:
                type_changes.append({
                    "field": old_field.name,
                    "old_type": old_field.type.value,
                    "new_type": new_field.type.value
                })
        
        return {
            "added_fields": list(added),
            "removed_fields": list(removed),
            "type_changes": type_changes,
            "drift_detected": bool(added or removed or type_changes)
        }
    
    def suggest_indexes(self, schema: SchemaDescriptor) -> List[str]:
        """
        Suggest indexes based on schema analysis.
        
        Args:
            schema: Schema descriptor
            
        Returns:
            List of suggested index field names
        """
        suggestions = []
        
        # Required fields are good index candidates
        for field in schema.get_required_fields():
            if field.type in (FieldType.INTEGER, FieldType.STRING):
                suggestions.append(field.name)
        
        # Fields with high coverage
        for field in schema.fields:
            coverage = 0
            if field.description and "Coverage:" in field.description:
                try:
                    coverage_str = field.description.split("Coverage: ")[1].split("%")[0]
                    coverage = float(coverage_str)
                except (IndexError, ValueError):
                    pass
            
            if coverage > 90 and field.type in (FieldType.INTEGER, FieldType.STRING):
                if field.name not in suggestions:
                    suggestions.append(field.name)
        
        return suggestions[:5]  # Top 5 suggestions
