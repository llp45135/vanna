"""
Custom exceptions for the NL2DSL subsystem.
"""

class VannaDSLError(Exception):
    """Base exception for all DSL related errors."""
    pass

class DSLCompileError(VannaDSLError):
    """
    Raised when the DSL cannot be compiled to SQL.
    Example: Invalid column reference, unsupported operator, type mismatch.
    """
    pass

class DSLValidationError(VannaDSLError):
    """
    Raised when the DSL structure itself is invalid provided by LLM.
    Wraps Pydantic validation errors or logical consistency errors.
    """
    pass
