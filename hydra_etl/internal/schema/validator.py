"""
Schema validation and drift detection.

Validates actual data against declared schema and detects drift.
"""

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from .descriptor import SchemaDescriptor, FieldDescriptor, FieldType
from .policies import DriftPolicy, ValidationPolicy, FieldPolicy


@dataclass
class ValidationResult:
    """Result of schema validation."""
    
    valid: bool
    """Whether validation passed."""
    
    errors: List[str]
    """List of validation errors."""
    
    warnings: List[str]
    """List of validation warnings."""
    
    missing_fields: List[str]
    """Fields declared but not found in data."""
    
    extra_fields: List[str]
    """Fields found in data but not declared in schema."""
    
    type_mismatches: Dict[str, str]
    """Fields with type mismatches: {field_name: mismatch_description}."""
    
    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.valid
    
    def add_error(self, message: str) -> None:
        """Add an error and mark as invalid."""
        self.errors.append(message)
        self.valid = False
    
    def add_warning(self, message: str) -> None:
        """Add a warning."""
        self.warnings.append(message)


class SchemaValidator:
    """
    Validates data against schema and detects drift.
    
    Examples:
        validator = SchemaValidator(schema_descriptor)
        result = validator.validate_document(document)
        
        if not result.valid:
            print(f"Validation errors: {result.errors}")
        
        if result.extra_fields:
            print(f"Schema drift detected: {result.extra_fields}")
    """
    
    def __init__(
        self,
        schema: SchemaDescriptor,
        drift_policy: Optional[DriftPolicy] = None,
        validation_policy: Optional[ValidationPolicy] = None,
        field_policy: Optional[FieldPolicy] = None
    ):
        """
        Initialize validator.
        
        Args:
            schema: Schema descriptor to validate against
            drift_policy: Override schema's drift policy
            validation_policy: Override schema's validation policy
            field_policy: Field-level policy
        """
        self.schema = schema
        self.drift_policy = drift_policy or DriftPolicy(schema.drift_policy)
        self.validation_policy = validation_policy or ValidationPolicy(schema.validation_policy)
        self.field_policy = field_policy or FieldPolicy()
    
    def validate_document(self, document: Dict[str, Any]) -> ValidationResult:
        """
        Validate a single document against schema.
        
        Args:
            document: Document to validate (flat dict)
            
        Returns:
            ValidationResult with errors, warnings, and drift info
        """
        result = ValidationResult(
            valid=True,
            errors=[],
            warnings=[],
            missing_fields=[],
            extra_fields=[],
            type_mismatches={}
        )
        
        # Get field names from document
        doc_fields = set(document.keys())
        schema_fields = {f.name for f in self.schema.fields}
        
        # Check for missing required fields
        for field in self.schema.get_required_fields():
            if field.name not in doc_fields:
                result.missing_fields.append(field.name)
                
                if self.validation_policy == ValidationPolicy.STRICT:
                    result.add_error(f"Required field '{field.name}' is missing")
                elif self.drift_policy == DriftPolicy.WARN:
                    result.add_warning(f"Required field '{field.name}' is missing")
        
        # Check for extra fields (drift)
        extra_fields = doc_fields - schema_fields
        if extra_fields:
            result.extra_fields = list(extra_fields)
            
            if self.drift_policy == DriftPolicy.FAIL:
                result.add_error(f"Unexpected fields found: {', '.join(extra_fields)}")
            elif self.drift_policy == DriftPolicy.WARN:
                result.add_warning(f"Unexpected fields found: {', '.join(extra_fields)}")
            # IGNORE and ADAPT don't trigger errors/warnings
        
        # Validate field types
        for field in self.schema.fields:
            if field.name in doc_fields:
                value = document[field.name]
                
                if not self._validate_field_type(field, value):
                    mismatch = f"Expected {field.type.value}, got {type(value).__name__}"
                    result.type_mismatches[field.name] = mismatch
                    
                    if self.validation_policy == ValidationPolicy.STRICT:
                        result.add_error(f"Type mismatch for '{field.name}': {mismatch}")
                    elif self.validation_policy == ValidationPolicy.BEST_EFFORT:
                        result.add_warning(f"Type mismatch for '{field.name}': {mismatch}")
        
        return result
    
    def validate_batch(self, documents: List[Dict[str, Any]]) -> List[ValidationResult]:
        """
        Validate multiple documents.
        
        Args:
            documents: List of documents to validate
            
        Returns:
            List of ValidationResult, one per document
        """
        return [self.validate_document(doc) for doc in documents]
    
    def detect_drift(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect schema drift across multiple documents.
        
        Args:
            documents: Sample of documents to analyze
            
        Returns:
            Dictionary with drift analysis:
            - new_fields: Fields appearing in data but not in schema
            - missing_fields: Schema fields never appearing in data
            - type_variations: Fields with multiple types
            - coverage: Percentage of documents containing each field
        """
        if not documents:
            return {
                "new_fields": [],
                "missing_fields": list({f.name for f in self.schema.fields}),
                "type_variations": {},
                "coverage": {}
            }
        
        # Track field presence and types
        field_counts: Dict[str, int] = {}
        field_types: Dict[str, Set[str]] = {}
        
        for doc in documents:
            for field_name, value in doc.items():
                field_counts[field_name] = field_counts.get(field_name, 0) + 1
                
                type_name = type(value).__name__
                if field_name not in field_types:
                    field_types[field_name] = set()
                field_types[field_name].add(type_name)
        
        # Identify drift
        schema_fields = {f.name for f in self.schema.fields}
        doc_fields = set(field_counts.keys())
        
        new_fields = list(doc_fields - schema_fields)
        missing_fields = list(schema_fields - doc_fields)
        
        # Calculate coverage
        total_docs = len(documents)
        coverage = {
            field: (count / total_docs) * 100
            for field, count in field_counts.items()
        }
        
        # Find type variations
        type_variations = {
            field: list(types)
            for field, types in field_types.items()
            if len(types) > 1
        }
        
        return {
            "new_fields": new_fields,
            "missing_fields": missing_fields,
            "type_variations": type_variations,
            "coverage": coverage,
            "total_documents": total_docs
        }
    
    def _validate_field_type(self, field: FieldDescriptor, value: Any) -> bool:
        """
        Validate that value matches expected field type.
        
        Args:
            field: Field descriptor
            value: Value to validate
            
        Returns:
            True if type matches, False otherwise
        """
        if value is None:
            return not field.required
        
        type_checks = {
            FieldType.STRING: lambda v: isinstance(v, str),
            FieldType.INTEGER: lambda v: isinstance(v, int) and not isinstance(v, bool),
            FieldType.FLOAT: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            FieldType.DECIMAL: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            FieldType.BOOLEAN: lambda v: isinstance(v, bool),
            FieldType.ARRAY: lambda v: isinstance(v, (list, tuple)),
            FieldType.OBJECT: lambda v: isinstance(v, dict),
            FieldType.JSON: lambda v: True,  # Any type acceptable
        }
        
        checker = type_checks.get(field.type)
        if not checker:
            return True  # Unknown type, accept
        
        return checker(value)
    
    def suggest_schema_update(self, documents: List[Dict[str, Any]]) -> SchemaDescriptor:
        """
        Suggest schema updates based on actual data.
        
        Analyzes documents and suggests new schema that covers all fields.
        Useful when drift_policy is ADAPT.
        
        Args:
            documents: Sample documents to analyze
            
        Returns:
            Updated SchemaDescriptor
        """
        drift = self.detect_drift(documents)
        
        # Create updated schema
        updated_schema = SchemaDescriptor(
            mode=self.schema.mode,
            fields=list(self.schema.fields),  # Copy existing
            drift_policy=self.schema.drift_policy,
            validation_policy=self.schema.validation_policy,
            sample_size=self.schema.sample_size
        )
        
        # Add new fields found in data
        for new_field in drift["new_fields"]:
            # Infer type from first occurrence
            field_type = self._infer_field_type(new_field, documents)
            
            field_desc = FieldDescriptor(
                name=new_field,
                type=field_type,
                required=False,  # New fields default to optional
                description=f"Auto-discovered field (coverage: {drift['coverage'].get(new_field, 0):.1f}%)"
            )
            
            updated_schema.add_field(field_desc)
        
        return updated_schema
    
    def _infer_field_type(self, field_name: str, documents: List[Dict[str, Any]]) -> FieldType:
        """
        Infer field type from sample documents.
        
        Args:
            field_name: Name of field to analyze
            documents: Sample documents
            
        Returns:
            Inferred FieldType
        """
        types_seen = set()
        
        for doc in documents:
            if field_name in doc:
                value = doc[field_name]
                if value is not None:
                    types_seen.add(type(value))
        
        if not types_seen:
            return FieldType.STRING  # Default
        
        # Priority: specific types first
        if bool in types_seen:
            return FieldType.BOOLEAN
        if int in types_seen and float not in types_seen:
            return FieldType.INTEGER
        if float in types_seen or int in types_seen:
            return FieldType.FLOAT
        if list in types_seen or tuple in types_seen:
            return FieldType.ARRAY
        if dict in types_seen:
            return FieldType.OBJECT
        
        return FieldType.STRING