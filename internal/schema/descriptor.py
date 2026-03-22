"""
Schema descriptor for declaring expected structure of atypical sources.

Provides declarative schema definition with support for:
- Nested fields (JSONPath)
- Array handling (flatten/explode)
- Optional vs required fields
- Type declarations
- Default values
"""

from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict
from enum import Enum


class FieldType(Enum):
    """Supported field types."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ARRAY = "array"
    OBJECT = "object"
    JSON = "json"


class ArrayHandling(Enum):
    """How to handle array fields."""
    KEEP = "keep"  # Keep as array column
    FLATTEN = "flatten"  # Create one column per array element
    EXPLODE = "explode"  # Create one row per array element
    JSON = "json"  # Convert to JSON string


@dataclass
class FieldDescriptor:
    """
    Describes a single field in the schema.
    
    Examples:
        # Simple field
        FieldDescriptor(name="user_id", type=FieldType.INTEGER, required=True)
        
        # Nested field (MongoDB)
        FieldDescriptor(
            name="customer_name",
            path="customer.name",
            type=FieldType.STRING
        )
        
        # Array field
        FieldDescriptor(
            name="tags",
            type=FieldType.ARRAY,
            array_handling=ArrayHandling.EXPLODE
        )
    """
    
    name: str
    """Column name in output."""
    
    type: FieldType
    """Field data type."""
    
    path: Optional[str] = None
    """JSONPath for nested fields (e.g., 'customer.address.city')."""
    
    required: bool = False
    """Whether field must be present."""
    
    default: Any = None
    """Default value if field is missing."""
    
    array_handling: Optional[ArrayHandling] = None
    """How to handle array fields."""
    
    constraints: Dict[str, Any] = field(default_factory=dict)
    """Additional constraints (min, max, pattern, etc.)."""
    
    description: Optional[str] = None
    """Human-readable description."""
    
    def __post_init__(self):
        """Validate field descriptor."""
        if self.type == FieldType.ARRAY and self.array_handling is None:
            self.array_handling = ArrayHandling.KEEP
        
        # If path not specified, use name
        if self.path is None:
            self.path = self.name
    
    def get_jsonpath(self) -> str:
        """
        Get JSONPath expression for this field.
        
        Returns:
            JSONPath string (e.g., '$.customer.name')
        """
        if not self.path:
            return f"$.{self.name}"
        
        # Handle array notation
        if "[]" in self.path:
            # Convert 'items[].product_id' to '$.items[*].product_id'
            path = self.path.replace("[]", "[*]")
            return f"$.{path}" if not path.startswith("$") else path
        
        # Simple path
        return f"$.{self.path}" if not self.path.startswith("$") else self.path
    
    def is_nested(self) -> bool:
        """Check if this field references a nested path."""
        return "." in (self.path or "")
    
    def is_array(self) -> bool:
        """Check if this field is an array."""
        return self.type == FieldType.ARRAY or "[]" in (self.path or "")


class SchemaMode(Enum):
    """Schema definition mode."""
    MANUAL = "manual"  # Fully manual schema definition
    INFER_STRICT = "infer_strict"  # Infer from sample, enforce strictly
    AUTO = "auto"  # Fully automatic inference
    HYBRID = "hybrid"  # Manual definition + auto-inference for missing


@dataclass
class SchemaDescriptor:
    """
    Complete schema descriptor for a data source.
    
    Examples:
        # Manual schema for MongoDB
        schema = SchemaDescriptor(
            mode=SchemaMode.MANUAL,
            fields=[
                FieldDescriptor(name="order_id", path="_id", type=FieldType.STRING, required=True),
                FieldDescriptor(name="customer_name", path="customer.name", type=FieldType.STRING),
                FieldDescriptor(name="total", type=FieldType.DECIMAL, required=True),
                FieldDescriptor(
                    name="items",
                    path="items[]",
                    type=FieldType.ARRAY,
                    array_handling=ArrayHandling.EXPLODE
                ),
            ],
            drift_policy="warn"
        )
    """
    
    mode: SchemaMode = SchemaMode.AUTO
    """How schema is defined/inferred."""
    
    fields: List[FieldDescriptor] = field(default_factory=list)
    """List of field descriptors."""
    
    drift_policy: str = "warn"
    """How to handle schema drift (fail/warn/ignore/adapt)."""
    
    validation_policy: str = "best_effort"
    """How to validate data (strict/best_effort/permissive)."""
    
    sample_size: int = 100
    """Number of documents to sample for inference."""
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""
    
    def get_field(self, name: str) -> Optional[FieldDescriptor]:
        """
        Get field descriptor by name.
        
        Args:
            name: Field name
            
        Returns:
            FieldDescriptor or None if not found
        """
        for f in self.fields:
            if f.name == name:
                return f
        return None
    
    def get_required_fields(self) -> List[FieldDescriptor]:
        """Get list of required fields."""
        return [f for f in self.fields if f.required]
    
    def get_nested_fields(self) -> List[FieldDescriptor]:
        """Get list of nested fields."""
        return [f for f in self.fields if f.is_nested()]
    
    def get_array_fields(self) -> List[FieldDescriptor]:
        """Get list of array fields."""
        return [f for f in self.fields if f.is_array()]
    
    def add_field(self, field_desc: FieldDescriptor) -> None:
        """
        Add a field to the schema.
        
        Args:
            field_desc: Field descriptor to add
        """
        # Check for duplicates
        if self.get_field(field_desc.name):
            raise ValueError(f"Field '{field_desc.name}' already exists in schema")
        
        self.fields.append(field_desc)
    
    def remove_field(self, name: str) -> bool:
        """
        Remove a field from the schema.
        
        Args:
            name: Field name
            
        Returns:
            True if field was removed, False if not found
        """
        for i, f in enumerate(self.fields):
            if f.name == name:
                del self.fields[i]
                return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert schema to dictionary representation.
        
        Returns:
            Dictionary representation suitable for YAML/JSON
        """
        return {
            "mode": self.mode.value,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type.value,
                    "path": f.path,
                    "required": f.required,
                    "default": f.default,
                    "array_handling": f.array_handling.value if f.array_handling else None,
                    "description": f.description,
                }
                for f in self.fields
            ],
            "drift_policy": self.drift_policy,
            "validation_policy": self.validation_policy,
            "sample_size": self.sample_size,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SchemaDescriptor':
        """
        Create SchemaDescriptor from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            SchemaDescriptor instance
        """
        fields = []
        for field_data in data.get("fields", []):
            field_desc = FieldDescriptor(
                name=field_data["name"],
                type=FieldType(field_data["type"]),
                path=field_data.get("path"),
                required=field_data.get("required", False),
                default=field_data.get("default"),
                array_handling=ArrayHandling(field_data["array_handling"]) if field_data.get("array_handling") else None,
                description=field_data.get("description"),
            )
            fields.append(field_desc)
        
        return cls(
            mode=SchemaMode(data.get("mode", "auto")),
            fields=fields,
            drift_policy=data.get("drift_policy", "warn"),
            validation_policy=data.get("validation_policy", "best_effort"),
            sample_size=data.get("sample_size", 100),
        )
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SchemaDescriptor(mode={self.mode.value}, "
            f"fields={len(self.fields)}, "
            f"drift_policy={self.drift_policy})"
        )