# Implementation Plan: NL2DSL MVP

**Branch**: `001-nl2dsl-mvp` | **Date**: 2025-12-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-nl2dsl-mvp/spec.md`

## Summary

This feature implements the **NL2DSL (Natural Language to Domain Specific Language)** architecture as a semantic layer for Vanna. It introduces a deterministic intermediate representation (JSON DSL) between the LLM and SQL generation to improve safety, consistency, and correctness. The implementation uses Pydantic for strict DSL validation and SQLAlchemy Core for secure, dialect-agnostic SQL compilation.

## Technical Context

**Language/Version**: Python 3.9+
**Primary Dependencies**: 
- `pydantic>=2.0` (for DSL Schema & Validation)
- `sqlalchemy>=1.4` (Core Expression Language for Compilation)
- `vanna` (existing core)
**Storage**: SQL Database (SQLite for verification with `ticket.db`, but design is Agnostic)
**Testing**: `pytest` for unit and integration tests
**Target Platform**: Python Library (`vanna` package)
**Performance Goals**: Compiler overhead < 50ms per query
**Constraints**: 
- MVP limited to Single Table analysis
- Strict prohibition of string concatenation for SQL generation
**Scale/Scope**: Core DSL primitives (Source, Filter, Agg, Sort, TimeGrain)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Type-Safe Contracts**: ✅ Pydantic models will define the DSL.
- **SQL Safety**: ✅ SQLAlchemy Core AST construction required.
- **Dialect Agnosticism**: ✅ SQLAlchemy backend handles dialect rendering.
- **Atomic & Declarative DSL**: ✅ DSL Schema defined as data-only (JSON).
- **Test-Driven Development**: ✅ Unit (Compiler) & Integration (Pipeline) tests planned.

## Project Structure

### Documentation (this feature)

```text
specs/001-nl2dsl-mvp/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (MVP usage guide)
├── contracts/           # Phase 1 output (API/Gateway contracts if any)
└── tasks.md             # Phase 2 output
```

### Source Code

```text
src/vanna/
├── dsl/                     # [NEW] DSL Subsystem
│   ├── __init__.py
│   ├── schema.py            # Pydantic Models (QueryDSL, Filter, etc.)
│   ├── compiler.py          # AST Builder (DSL -> SQLAlchemy)
│   ├── errors.py            # Custom Exceptions
│   └── types.py             # Shared TypeDefs
└── core/
    └── nl2dsl.py            # [NEW] Integration logic (Pipeline)

tests/
├── dsl/                     # [NEW] Unit tests for DSL
│   ├── test_schema.py
│   └── test_compiler.py
└── integration/
    └── test_nl2dsl_flow.py  # [NEW] End-to-end tests with ticket.db
```

**Structure Decision**: Created a new `dsl` package within `vanna` to isolate the semantic layer, maintaining clean separation from the existing RAG/VectorDB logic. Integration happens in `core`.

## Complexity Tracking

No violations of the constitution. The introduction of `pydantic` and `sqlalchemy` (if not already strictly used this way) is necessary for the "Type-Safe" and "SQL Safe" principles.
