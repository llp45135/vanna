<!--
SYNC IMPACT REPORT
Version Change: 1.0.0 -> 1.1.0
Modified Principles:
- N/A
Added Sections:
- Technical Standards: Added "Package & Env Management" (uv)
Templates Status:
- plan-template.md: ✅
- spec-template.md: ✅
- tasks-template.md: ✅
TODOs: None.
-->

# Vanna Constitution

## Core Principles

### I. Type-Safe Contracts
All internal data structures, especially those facilitating communication between LLM and Compiler, MUST be defined as Pydantic models. This ensures strict type validation and effectively prevents hallucinations in structural data. The "DSL Schema" is the single source of truth.

### II. SQL Safety
Generation of SQL MUST be performed using SQLAlchemy Core (Expression Language) via Abstract Syntax Trees (AST). Direct string concatenation or template-based SQL generation (outside of controlled debugging) is STRICTLY PROHIBITED to prevent SQL injection vulnerabilities.

### III. Dialect Agnosticism
Business logic and DSL compilation MUST remain database-dialect agnostic. Dialect-specific rendering is handled solely by the SQLAlchemy compilation layer. The system must support generating SQL for multiple backends (e.g., PostgreSQL, MySQL, SQLite) without changes to the core compiler logic.

### IV. Atomic & Declarative DSL
The intermediate representation (DSL) MUST be atomic and declarative. It should describe "what" data is needed (Filters, Aggregations, Sorts) rather than "how" to retrieve it. This separation of concerns allows the compiler to handle optimization and dialect differences.

### V. Test-Driven Development
All features must include comprehensive tests. Unit tests for the compiler are mandatory to ensure DSL-to-SQL correctness across supported dialects. Integration tests are required to verify the end-to-end "NL -> DSL -> SQL -> Data" flow.

## Technical Standards

**Language**: Python 3.9+ (Verified via setup contexts or general compatibility needs).
**Core Libraries**: Pydantic v2+, SQLAlchemy 1.4/2.0+ Core.
**Package & Env Management**: `uv` (Mandatory for dependency resolution and virtual environment management).
**Style**: Adhere to PEP 8; use Type Hints everywhere (`typing` or standard collection types).
**Documentation**: All public APIs and DSL models must have docstrings.

## Development Workflow

1.  **Design First**: For non-trivial changes, update the DSL Schema definition (Pydantic models) before implementation.
2.  **Code Review**: All changes require PR review. Focus on adherence to Type Safety and SQL Safety principles.
3.  **Testing Gates**: CI must pass all unit and integration tests before merge.

## Governance

**Amendment Policy**: Changes to Core Principles (especially DSL or Security constraints) require an RFC (Request for Comments) process and approval from core maintainers.

**Versioning**: Follow Semantic Versioning (MAJOR.MINOR.PATCH).
*   **MAJOR**: Breaking changes to the DSL Schema or public API.
*   **MINOR**: New DSL features (e.g., new operators) or backwards-compatible compiler improvements, or new mandatory tooling.
*   **PATCH**: Bug fixes or internal refactoring.

**Version**: 1.1.0 | **Ratified**: 2025-12-15 | **Last Amended**: 2025-12-15
