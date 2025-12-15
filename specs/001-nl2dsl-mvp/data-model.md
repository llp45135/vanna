# Data Model: NL2DSL MVP

**Status**: Draft
**Context**: This defines the Pydantic models for the DSL.

## 1. Domain Entities

### QueryDSL (Root)
The container for a single analytical question.

| Field | Type | Required | Description |
|---|---|---|---|
| `table` | `str` | Yes | Target table name. |
| `filters` | `List[Filter]` | No | List of conditions (AND logic). |
| `aggregates` | `List[Aggregation]` | No | Metrics to calculate. |
| `group_by` | `List[str]` | No | Dimensions to group by. |
| `time_grains` | `List[TimeGrain]` | No | Time truncations (e.g. Monthly). |
| `sorts` | `List[Sort]` | No | Ordering instructions. |
| `limit` | `int` | No | Row limit (1-1000). |

### Filter
Atomic condition.

| Field | Type | Description | Validation |
|---|---|---|---|
| `field` | `str` | Column Name | Must exist in metadata. |
| `op` | `Enum` | Operator | `eq, neq, gt, lt, gte, lte, like, in` |
| `value` | `Union[str, int, float, List]` | Comparison Value | Date strings must be ISO8601. |

### Aggregation
Metric definition.

| Field | Type | Description |
|---|---|---|
| `func` | `Enum` | `sum, count, avg, min, max, count_distinct` |
| `field` | `str` | Column to aggregate (or `*`). |
| `alias` | `str` | Output column name (optional). |

### TimeGrain
Time dimension truncation.

| Field | Type | Description |
|---|---|---|
| `field` | `str` | Date/Time column. |
| `grain` | `Enum` | `year, quarter, month, week, day` |
| `alias` | `str` | Output column name. |

## 2. Validation Rules

1.  **ISO 8601**: `Filter.value` must be validated by `datetime.fromisoformat()` if the target column is known to be a date type (though strictly, the DSL validator might just check string format if metadata isn't strictly coupled yet. MVP: Check format).
2.  **Logic**: `group_by` must contain all `TimeGrain.alias` if defined.
3.  **Safety**: `limit` capped at 1000.
