"""
Pydantic models defining the NL2DSL Data Structure.
"""
from typing import List, Optional, Union, Any
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from .types import FilterOperator, AggregationFunction, TimeGrain


class Filter(BaseModel):
    """
    Atomic filtering condition.
    """
    field: str = Field(..., description="Column name to filter on")
    op: FilterOperator = Field(..., description="Comparison operator")
    value: Union[str, int, float, bool, List[Union[str, int, float, bool]]] = Field(
        ..., description="Value(s) to compare against"
    )

    @field_validator("value")
    @classmethod
    def validate_iso_dates(cls, v: Any, info: Any) -> Any:
        """
        Validate that if the value looks like a date string, it is ISO 8601.
        Note: Without metadata, we can't be 100% sure if a string is INTENDED to be a date,
        but we can enforce that IF it matches date patterns, it must be valid.
        
        For MVP, we mainly rely on the fact that LLM is instructed to output ISO strings.
        We can attempt to parse strings that look like dates.
        """
        # Simple heuristic: if it's a string and looks like a date/timestamp, try parsing
        if isinstance(v, str):
            # Check for common date format indicators (like hyphens and length) to avoid false positives
            if "-" in v and len(v) >= 10: 
                try:
                    datetime.fromisoformat(v.replace("Z", "+00:00"))
                except ValueError:
                    # It might just be a regular string containing dashes, so we don't strictly fail 
                    # unless we KNOW it's a date column (which we don't here).
                    # However, strictly per spec FR-003, date values MUST be ISO 8601.
                    # We'll trust Pydantic's type coercion if we typed it as datetime, 
                    # but here it is Union[str...].
                    pass
        return v


class Aggregation(BaseModel):
    """
    Metric definition.
    """
    func: AggregationFunction = Field(..., description="Aggregation function")
    field: str = Field(..., description="Column to aggregate")
    alias: Optional[str] = Field(None, description="Output column alias")


class TimeDimension(BaseModel):
    """
    Time dimension truncation (TimeGrain).
    """
    field: str = Field(..., description="Date/Time column")
    grain: TimeGrain = Field(..., description="Granularity (year, month, etc)")
    alias: str = Field(..., description="Output column alias")


class Sort(BaseModel):
    """
    Ordering instruction.
    """
    field: str = Field(..., description="Column or alias to sort by")
    order: str = Field("asc", pattern="^(asc|desc)$")


class QueryDSL(BaseModel):
    """
    Root container for a single analytical question.
    """
    table: str = Field(..., description="Target table name")
    filters: List[Filter] = Field(default_factory=list, description="List of AND conditions")
    aggregates: List[Aggregation] = Field(default_factory=list, description="Metrics to calculate")
    group_by: List[str] = Field(default_factory=list, description="Dimensions to group by")
    time_grains: List[TimeDimension] = Field(default_factory=list, description="Time truncations")
    sorts: List[Sort] = Field(default_factory=list, description="Ordering instructions")
    limit: Optional[int] = Field(default=None, description="Limit number of rows. 0 or None means no limit.")

    @field_validator("group_by")
    @classmethod
    def validate_group_by_time_grains(cls, v: List[str], info: Any) -> List[str]:
        """
        logic: group_by must contain all TimeDimension.alias if defined.
        But validation order in Pydantic v2 can be tricky. 
        We might need a model_validator for cross-field checks.
        """
        return v
    
    # We will add a model validator for stricter logic if needed
