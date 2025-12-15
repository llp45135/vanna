# Tasks: NL2DSL MVP

**Feature**: `001-nl2dsl-mvp`
**Status**: Generated

## Phase 1: Setup

- [x] T001 Create DSL package structure `src/vanna/dsl/` and `tests/dsl/`

## Phase 2: Foundation (Blocking)

- [x] T002 Implement custom exceptions in `src/vanna/dsl/errors.py`
- [x] T003 Implement shared types in `src/vanna/dsl/types.py`
- [x] T004 Implement DSL Pydantic models in `src/vanna/dsl/schema.py` (QueryDSL, Filter, Aggregation) according to `data-model.md`
- [x] T005 [P] Create unit tests for schema validation in `tests/dsl/test_schema.py`

## Phase 3: User Story 1 - Basic Single-Table Analysis

**Goal**: Enable natural language questions to be compiled into valid SQL for a single table.
**Test Criteria**: `tests/integration/test_nl2dsl_flow.py` passes happy path with `ticket.db`.

- [x] T006 [US1] Implement TimeGrain compiler strategies (SQLite support) in `src/vanna/dsl/compiler.py`
- [x] T007 [US1] Implement main `DSLCompiler` class in `src/vanna/dsl/compiler.py` (using SQLAlchemy Core)
- [x] T008 [P] [US1] Create unit tests for compiler in `tests/dsl/test_compiler.py`
- [x] T009 [US1] Implement `generate_dsl` (Prompt Engineering) and `compile_dsl` in `src/vanna/core/nl2dsl.py`
- [x] T010 [US1] Implement `run_nl2dsl` integration flow in `src/vanna/core/nl2dsl.py` (Connecting Vanna LLM -> DSL -> SQL)
- [x] T011 [US1] Implement Golden Q&A loader in `src/vanna/dsl/evaluation.py` (FR-008)
- [/] T012 [P] [US1] Create integration test `tests/integration/test_nl2dsl_flow.py` (Happy Path)

## Phase 4: User Story 2 - Schema Validation (Safety)

**Goal**: Prevent hallucinations by validating DSL against actual database metadata.
**Test Criteria**: System throws `DSLCompileError` when DSL references non-existent columns.

- [x] T013 [US2] Enhance `DSLCompiler` to validate columns against SQLAlchemy Metadata in `src/vanna/dsl/compiler.py`
- [x] T014 [US2] Update `test_compiler.py` to test schema validation errors (Schema Awareness)
- [/] T015 [US2] Implement Retry Logic (1 attempt) in `src/vanna/core/nl2dsl.py` (FR-005)

## Phase 5: Polish & Cross-Cutting

- [x] T016 Add docstrings to public API in `src/vanna/core/nl2dsl.py` covering `contracts/api.md`
- [x] T017 Verify Constitution Compliance (No string concatenation, Type Safety)

## Dependencies

- Phase 2 must complete before Phase 3.
- T004 (Schema) is required for T007 (Compiler).
- T007 (Compiler) is required for T009 (Integration).
- T013 modifies T007, so Phase 4 depends on Phase 3.

## Implementation Strategy

We will build the `dsl` package first (Foundation), then the Compiler (US1 core), then integrate it into Vanna (US1 integration), and finally add the validation safety net (US2).
