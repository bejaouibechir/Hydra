"""
Unit tests for Schema Layer (Phase 2).

Tests schema descriptor, policies, and validation.
"""

import pytest
from hydra_etl.internal.schema import (
    SchemaDescriptor,
    FieldDescriptor,
    FieldType,
    ArrayHandling,
    SchemaMode,
    DriftPolicy,
    ValidationPolicy,
    SchemaValidator,
    PolicyFactory
)


# ============================================================
# Tests FieldDescriptor
# ============================================================

def test_field_descriptor_simple():
    """Test simple field creation."""
    field = FieldDescriptor(
        name="user_id",
        type=FieldType.INTEGER,
        required=True
    )
    
    assert field.name == "user_id"
    assert field.type == FieldType.INTEGER
    assert field.required is True
    assert field.path == "user_id"  # Auto-set


def test_field_descriptor_nested():
    """Test nested field with JSONPath."""
    field = FieldDescriptor(
        name="customer_name",
        path="customer.name",
        type=FieldType.STRING
    )
    
    assert field.name == "customer_name"
    assert field.path == "customer.name"
    assert field.is_nested() is True
    assert field.get_jsonpath() == "$.customer.name"


def test_field_descriptor_array():
    """Test array field."""
    field = FieldDescriptor(
        name="items",
        path="items[]",
        type=FieldType.ARRAY,
        array_handling=ArrayHandling.EXPLODE
    )
    
    assert field.is_array() is True
    assert field.array_handling == ArrayHandling.EXPLODE
    assert "[*]" in field.get_jsonpath()


# ============================================================
# Tests SchemaDescriptor
# ============================================================

def test_schema_descriptor_creation():
    """Test schema creation."""
    schema = SchemaDescriptor(
        mode=SchemaMode.MANUAL,
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER, required=True),
            FieldDescriptor(name="name", type=FieldType.STRING),
        ],
        drift_policy="warn"
    )
    
    assert schema.mode == SchemaMode.MANUAL
    assert len(schema.fields) == 2
    assert schema.drift_policy == "warn"


def test_schema_get_field():
    """Test field lookup."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER),
            FieldDescriptor(name="name", type=FieldType.STRING),
        ]
    )
    
    field = schema.get_field("name")
    assert field is not None
    assert field.type == FieldType.STRING
    
    assert schema.get_field("unknown") is None


def test_schema_required_fields():
    """Test required fields filtering."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER, required=True),
            FieldDescriptor(name="name", type=FieldType.STRING, required=False),
            FieldDescriptor(name="email", type=FieldType.STRING, required=True),
        ]
    )
    
    required = schema.get_required_fields()
    assert len(required) == 2
    assert {f.name for f in required} == {"id", "email"}


def test_schema_to_dict():
    """Test schema serialization."""
    schema = SchemaDescriptor(
        mode=SchemaMode.MANUAL,
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER, required=True)
        ],
        drift_policy="fail"
    )
    
    data = schema.to_dict()
    
    assert data["mode"] == "manual"
    assert data["drift_policy"] == "fail"
    assert len(data["fields"]) == 1
    assert data["fields"][0]["name"] == "id"


def test_schema_from_dict():
    """Test schema deserialization."""
    data = {
        "mode": "manual",
        "fields": [
            {
                "name": "id",
                "type": "integer",
                "required": True
            }
        ],
        "drift_policy": "warn"
    }
    
    schema = SchemaDescriptor.from_dict(data)
    
    assert schema.mode == SchemaMode.MANUAL
    assert len(schema.fields) == 1
    assert schema.fields[0].name == "id"


# ============================================================
# Tests Policies
# ============================================================

def test_policy_factory_strict():
    """Test strict policy creation."""
    drift, validation, field = PolicyFactory.strict()
    
    assert drift == DriftPolicy.FAIL
    assert validation == ValidationPolicy.STRICT
    assert field.on_missing == "fail"


def test_policy_factory_lenient():
    """Test lenient policy creation."""
    drift, validation, field = PolicyFactory.lenient()
    
    assert drift == DriftPolicy.WARN
    assert validation == ValidationPolicy.BEST_EFFORT
    assert field.on_type_mismatch == "coerce"


# ============================================================
# Tests SchemaValidator
# ============================================================

def test_validator_valid_document():
    """Test validation of valid document."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER, required=True),
            FieldDescriptor(name="name", type=FieldType.STRING),
        ]
    )
    
    validator = SchemaValidator(schema)
    
    document = {"id": 1, "name": "Alice"}
    result = validator.validate_document(document)
    
    assert result.valid is True
    assert len(result.errors) == 0


def test_validator_missing_required_field():
    """Test validation with missing required field."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER, required=True),
        ],
        validation_policy="strict"
    )
    
    validator = SchemaValidator(schema)
    
    document = {"name": "Alice"}  # Missing 'id'
    result = validator.validate_document(document)
    
    assert result.valid is False
    assert "id" in result.missing_fields
    assert len(result.errors) > 0


def test_validator_extra_fields_fail():
    """Test drift detection with FAIL policy."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER),
        ],
        drift_policy="fail"
    )
    
    validator = SchemaValidator(schema)
    
    document = {"id": 1, "extra_field": "unexpected"}
    result = validator.validate_document(document)
    
    assert result.valid is False
    assert "extra_field" in result.extra_fields


def test_validator_extra_fields_warn():
    """Test drift detection with WARN policy."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER),
        ],
        drift_policy="warn"
    )
    
    validator = SchemaValidator(schema)
    
    document = {"id": 1, "extra_field": "unexpected"}
    result = validator.validate_document(document)
    
    assert result.valid is True  # Warning, not error
    assert "extra_field" in result.extra_fields
    assert len(result.warnings) > 0


def test_validator_type_mismatch():
    """Test type validation."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER),
        ],
        validation_policy="strict"
    )
    
    validator = SchemaValidator(schema)
    
    document = {"id": "not_an_integer"}
    result = validator.validate_document(document)
    
    assert result.valid is False
    assert "id" in result.type_mismatches


def test_validator_detect_drift():
    """Test drift detection across multiple documents."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER),
            FieldDescriptor(name="name", type=FieldType.STRING),
        ]
    )
    
    validator = SchemaValidator(schema)
    
    documents = [
        {"id": 1, "name": "Alice", "age": 30},  # Extra field 'age'
        {"id": 2, "name": "Bob", "age": 25},
        {"id": 3, "name": "Charlie"},  # No 'age'
    ]
    
    drift = validator.detect_drift(documents)
    
    assert "age" in drift["new_fields"]
    assert drift["coverage"]["age"] == pytest.approx(66.67, rel=0.1)


def test_validator_suggest_schema_update():
    """Test automatic schema update suggestion."""
    schema = SchemaDescriptor(
        fields=[
            FieldDescriptor(name="id", type=FieldType.INTEGER),
        ]
    )
    
    validator = SchemaValidator(schema)
    
    documents = [
        {"id": 1, "name": "Alice", "active": True},
        {"id": 2, "name": "Bob", "active": False},
    ]
    
    updated_schema = validator.suggest_schema_update(documents)
    
    assert len(updated_schema.fields) == 3  # id + name + active
    assert updated_schema.get_field("name") is not None
    assert updated_schema.get_field("active") is not None


# ============================================================
# Integration Test
# ============================================================

def test_schema_validation_integration():
    """Full integration test: schema definition → validation → drift detection."""
    # Define schema
    schema = SchemaDescriptor(
        mode=SchemaMode.INFER_STRICT,
        fields=[
            FieldDescriptor(name="user_id", type=FieldType.INTEGER, required=True),
            FieldDescriptor(name="email", type=FieldType.STRING, required=True),
            FieldDescriptor(name="age", type=FieldType.INTEGER),
        ],
        drift_policy="warn",
        validation_policy="best_effort"
    )
    
    # Create validator
    validator = SchemaValidator(schema)
    
    # Validate good document
    good_doc = {"user_id": 1, "email": "alice@example.com", "age": 30}
    result = validator.validate_document(good_doc)
    assert result.valid is True
    
    # Validate document with drift
    drift_doc = {"user_id": 2, "email": "bob@example.com", "age": 25, "city": "Paris"}
    result = validator.validate_document(drift_doc)
    assert result.valid is True  # Warn, don't fail
    assert "city" in result.extra_fields
    assert len(result.warnings) > 0
    
    # Detect drift across batch
    documents = [good_doc, drift_doc]
    drift = validator.detect_drift(documents)
    assert "city" in drift["new_fields"]
    
    # Suggest update
    updated = validator.suggest_schema_update(documents)
    assert updated.get_field("city") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])