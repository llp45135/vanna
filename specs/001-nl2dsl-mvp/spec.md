# Feature Specification: NL2DSL MVP

**Feature Branch**: `001-nl2dsl-mvp`
**Created**: 2025-12-15
**Status**: Draft
**Input**: User description: "Implement NL2DSL MVP according to semantic enhanced vanna proposal"

## Clarifications

### Session 2025-12-15
- Q: What format should Date/Time values use in the DSL? → A: **ISO 8601 Strings** (e.g., "2023-12-31T23:59:59"). The Compiler will handle parsing and dialect-specific casting.
- Q: Which Time Granularities must be supported? → A: **Standard Analytics Set** (Year, Quarter, Month, Week, Day).
- Q: How should validation errors be handled in the MVP? → A: **Simple Retry (1 Attempt)**. If validation fails, the error is fed back to the LLM for one correction attempt before failing.

## User Scenarios & Testing

### User Story 1 - Basic Single-Table Analysis (Priority: P1)

As a data analyst, I want to ask natural language questions about a single table so that I get accurate results guaranteed by a deterministic compiler.

**Why this priority**: this is the core MVP functionality to validate the NL2DSL architecture.

**Independent Test**: Can be tested by setting up the system with a single table metadata, asking "What is the total sales by region?", and verifying the generated intermediate DSL and final SQL.

**Acceptance Scenarios**:

1. **Given** a system configured with 'orders' table metadata, **When** I ask "Show me total amount by region", **Then** the system generates a correct structured DSL, compiles it to a `SELECT region, SUM(amount) ... GROUP BY region` SQL, and returns the data.
2. **Given** a query with specific filters (e.g., "sales in 2024"), **When** I ask the question, **Then** the generated DSL includes the correct filter logic and the SQL WHERE clause reflects this.

---

### User Story 2 - Schema Validation prevents Hallucinations (Priority: P2)

As a developer, I want the system to reject invalid LLM outputs before they hit the database, so that I don't run broken or dangerous SQL.

**Why this priority**: Safety and reliability are the main selling points of this architecture over pure NL2SQL.

**Independent Test**: Can be tested by mocking the LLM response to return invalid DSL (e.g., missing fields, wrong types) and asserting the pipeline catches the error.

**Acceptance Scenarios**:

1. **Given** the LLM generates a DSL with a non-existent operator "jump", **When** the validation step runs, **Then** a validation error is raised and execution stops (or triggers retry).
2. **Given** the LLM generates a DSL referencing a column "profit" that doesn't exist in the metadata, **When** the Compiler runs, **Then** a schema violation error is raised preventing SQL generation.

---

### Edge Cases

- **Unsupported Operator**: If the LLM generates a filter operator not supported by the DSL definition, the system MUST catch this at the validation stage and return a descriptive error.
- **Type Mismatch**: If the DSL provides a string value for an integer column (that cannot be coerced), the validation MUST fail.
- **SQL Injection Attempt**: If a malicious user input causes the LLM to put SQL syntax into a string value (e.g., `value: "'; DROP TABLE ..."`), the Compiler MUST treat it strictly as a literal value via parameter binding, preventing execution.
- **Empty/Garbage Output**: If the LLM returns non-JSON text or empty output, the pipeline MUST detect this as a generation failure.

## Requirements

### Functional Requirements

- **FR-001**: System MUST define a strict, typed **Data Structure** (DSL) that includes `Source`, `Filter`, `Aggregation`, `Sort`, and `TimeGrain` primitives. **Supported Time Grains: Year, Quarter, Month, Week, Day.**
- **FR-002**: System MUST implement a **DSL Compiler** component that accepts a valid DSL object and Database Metadata, and produces valid SQL for the target dialect.
- **FR-003**: The Compiler MUST support, at minimum, equality/inequality, range comparison (gt/lt), set inclusion (in), and pattern matching (like) operators. **Date/Time values MUST be provided as ISO 8601 strings, which the Compiler will cast to appropriate DB types.**
- **FR-004**: The Compiler MUST support standard aggregation functions: Sum, Count, Average, Min, Max, Count Distinct.
- **FR-005**: System MUST provide an integration workflow that orchestrates: Retrieve Context -> Prompt LLM for structured DSL -> Validate DSL Structure -> **(If Invalid) Retry Once with Error Feedback** -> Compile to SQL -> Execute SQL.
- **FR-006**: The Prompt Engineering MUST be designed to instruct the LLM to output only the defined structured format.
- **FR-007**: System MUST use secure **parameter binding** or AST-based query construction to prevent SQL injection; direct string concatenation of user-supplied values into the SQL string is PROHIBITED.
- **FR-008**: System MUST support the ingestion/utilization of **"Golden Q&A Pairs"** (Natural Language -> Expected DSL) to enable Few-Shot Prompting, which is critical for schema adherence.

### Key Entities

- **QueryDSL**: The structured, intermediate representation of the user's intent (JSON-interpretable).
- **DSLCompiler**: The engine that transforms QueryDSL into the target SQL Dialect.
- **Metrics/Metadata Store**: The definitive source of truth for table schemas and (optionally) predefined metrics.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of syntactically valid DSLs (those passing schema validation) generated by the system must compile to valid SQL for the target database.
- **SC-002**: The overhead of the Compiler step (DSL -> SQL) must be less than 50ms for typical queries.
- **SC-003**: System detects and rejects 100% of queries referencing non-existent columns (Schema Awareness) before SQL execution command is sent to the database.
- **SC-004**: A test set of at least 20 "Golden Questions" (covering all supported operators and aggregations) correctly generates the expected DSL.

## Assumptions

- We are targeting a single-table scenario for this MVP. Auto-Joins are out of scope.
- The hosting environment provides a capable LLM (e.g., GPT-4 class) adequate for JSON generation.
- Database metadata (table constraints, column types) is available to the system application at runtime.
