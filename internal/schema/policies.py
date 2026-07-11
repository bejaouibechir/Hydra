"""
Schema validation and drift policies.

Defines how Hydra handles schema mismatches, missing fields,
and unexpected data in atypical sources.
"""

from enum import Enum
from typing import Any, Optional


class DriftPolicy(Enum):
    """
    Policy for handling schema drift (when actual data differs from expected schema).
    
    Examples:
        - New field appears in MongoDB document
        - Expected field is missing
        - Field type differs from declaration
    """
    
    FAIL = "fail"
    """Raise exception immediately on any schema drift."""
    
    WARN = "warn"
    """Log warning but continue processing."""
    
    IGNORE = "ignore"
    """Silently ignore schema drift."""
    
    ADAPT = "adapt"
    """Dynamically adapt schema to match actual data."""


class ValidationPolicy(Enum):
    """
    Policy for validating data during extraction/loading.
    """
    
    STRICT = "strict"
    """All fields must match schema exactly (type, required, constraints)."""
    
    BEST_EFFORT = "best_effort"
    """Try to coerce types, use defaults for missing fields."""
    
    PERMISSIVE = "permissive"
    """Accept any data, minimal validation."""


class FieldPolicy:
    """
    Policy for handling a specific field's issues.
    """
    
    def __init__(
        self,
        on_missing: str = "null",  # null | default | fail | warn
        on_type_mismatch: str = "coerce",  # coerce | fail | warn | null
        on_constraint_violation: str = "warn"  # fail | warn | ignore
    ):
        self.on_missing = on_missing
        self.on_type_mismatch = on_type_mismatch
        self.on_constraint_violation = on_constraint_violation
    
    def handle_missing(self, field_name: str, default_value: Any = None) -> Any:
        """
        Handle missing field according to policy.
        
        Args:
            field_name: Name of missing field
            default_value: Default value if defined
            
        Returns:
            Value to use for missing field
            
        Raises:
            ValueError: If policy is 'fail'
        """
        if self.on_missing == "fail":
            raise ValueError(f"Required field '{field_name}' is missing")
        elif self.on_missing == "warn":
            # TODO: Log warning
            return None
        elif self.on_missing == "default":
            return default_value
        else:  # null
            return None
    
    def handle_type_mismatch(
        self,
        field_name: str,
        expected_type: str,
        actual_value: Any
    ) -> Any:
        """
        Handle type mismatch according to policy.
        
        Args:
            field_name: Name of field
            expected_type: Expected type name
            actual_value: Actual value with wrong type
            
        Returns:
            Coerced value or None
            
        Raises:
            TypeError: If policy is 'fail'
        """
        if self.on_type_mismatch == "fail":
            raise TypeError(
                f"Field '{field_name}' type mismatch: "
                f"expected {expected_type}, got {type(actual_value).__name__}"
            )
        elif self.on_type_mismatch == "warn":
            # TODO: Log warning
            return None
        elif self.on_type_mismatch == "null":
            return None
        else:  # coerce
            return self._coerce_type(expected_type, actual_value)
    
    def _coerce_type(self, expected_type: str, value: Any) -> Any:
        """
        Try to coerce value to expected type.
        
        Args:
            expected_type: Target type
            value: Value to coerce
            
        Returns:
            Coerced value or None if coercion fails
        """
        if value is None:
            return None
        
        try:
            if expected_type in ("string", "str"):
                return str(value)
            elif expected_type in ("integer", "int"):
                return int(value)
            elif expected_type in ("float", "decimal", "number"):
                return float(value)
            elif expected_type in ("boolean", "bool"):
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
            else:
                return value
        except (ValueError, TypeError):
            return None


class PolicyFactory:
    """
    Factory for creating common policy combinations.
    """
    
    @staticmethod
    def strict() -> tuple[DriftPolicy, ValidationPolicy, FieldPolicy]:
        """
        Strict policy: fail fast on any issue.
        
        Use case: Production pipelines with well-defined schemas.
        """
        return (
            DriftPolicy.FAIL,
            ValidationPolicy.STRICT,
            FieldPolicy(
                on_missing="fail",
                on_type_mismatch="fail",
                on_constraint_violation="fail"
            )
        )
    
    @staticmethod
    def lenient() -> tuple[DriftPolicy, ValidationPolicy, FieldPolicy]:
        """
        Lenient policy: try to fix issues, warn on problems.
        
        Use case: Development, exploration, dirty data.
        """
        return (
            DriftPolicy.WARN,
            ValidationPolicy.BEST_EFFORT,
            FieldPolicy(
                on_missing="default",
                on_type_mismatch="coerce",
                on_constraint_violation="warn"
            )
        )
    
    @staticmethod
    def adaptive() -> tuple[DriftPolicy, ValidationPolicy, FieldPolicy]:
        """
        Adaptive policy: adjust to actual data structure.
        
        Use case: Schema discovery, evolving sources.
        """
        return (
            DriftPolicy.ADAPT,
            ValidationPolicy.PERMISSIVE,
            FieldPolicy(
                on_missing="null",
                on_type_mismatch="coerce",
                on_constraint_violation="ignore"
            )
        )