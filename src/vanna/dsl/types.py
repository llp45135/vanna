"""
Shared type definitions and Enums for the NL2DSL subsystem.
"""
from enum import Enum


class FilterOperator(str, Enum):
    """Supported operators for filtering."""
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    LIKE = "like"
    IN = "in"


class AggregationFunction(str, Enum):
    """Supported aggregation functions."""
    SUM = "sum"
    COUNT = "count"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT_DISTINCT = "count_distinct"


class TimeGrain(str, Enum):
    """Supported time granularities."""
    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
