# Research: NL2DSL MVP Implementation details

## summary

This document captures decisions regarding "Golden Q&A" formats and cross-dialect Time Granularity implementation.

## 1. Golden Q&A Pair Format

**Context**: FR-008 requires ingestion of Q&A pairs for Few-Shot prompting.
**Decision**: Use **JSONL (JSON Lines)** format.
**Rationale**: 
- Streaming-friendly for large datasets.
- Human-readable enough for debugging.
- Easy to append to `vanna` training data.

**Schema**:
```json
{
  "question": "What is the total sales by region?",
  "expected_dsl": {
    "table": "orders",
    "aggregates": [{"func": "sum", "field": "amount", "alias": "total_sales"}],
    "group_by": ["region"]
  },
  "meta": {"verified_by": "human", "date": "2025-12-15"}
}
```

**Alternatives Considered**:
- **YAML**: Better readability, but slower parsing for large sets.
- **CSV**: Poor support for nested JSON objects (the `expected_dsl` field).

## 2. Time Granularity Compilation (SQLite vs Others)

**Context**: FR-001 supports `Year, Quarter, Month, Week, Day`. MVP targets SQLite (`ticket.db`) but system must be Agnostic.
**Problem**: SQLAlchemy's `extract` returns integers (e.g. Month=1). Analytics usually requires Truncation (e.g. Month=2023-01-01). `date_trunc` is Postgres-only. SQLite uses `strftime`.

**Decision**: Implement a **Dialect-Specific Compiler Strategy** for TimeGrain.
- Define a generic `TimeGrainCompiler` interface.
- Implement `SQLiteTimeGrainCompiler` using `func.strftime`.
- Implement `GenericTimeGrainCompiler` (using `extract` or `date_trunc` where available) as fallback.

**Examples**:
- **Month (SQLite)**: `func.strftime('%Y-%m', col)`
- **Month (Postgres)**: `func.date_trunc('month', col)`

**Rationale**: Adheres to Constitution Principle III (Dialect Agnosticism) by isolating the dialect logic in the compiler layer, keeping the DSL pure.

## 3. Pydantic Schema Strategy

**Context**: Need strict validation.
**Decision**: Use `pydantic.Discriminator` for polymorphic Filters if needed, or keeping it flat for MVP.
**Design**:
- `Filter` model will use a simple `op/field/value` structure.
- `Value` field will use `Union[str, int, float, List[...]]` with strict type casting enabled.
- **Validation**: Custom `@field_validator` for Date strings to enforce ISO 8601 (FR-003).
