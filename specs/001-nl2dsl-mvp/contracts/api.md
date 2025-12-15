# API Contract: NL2DSL

## Python API

### `vanna.core.nl2dsl`

#### `generate_dsl(question: str) -> dict`
Generates the intermediate JSON DSL from natural language.

- **Input**: Natural language question.
- **Output**: Dictionary matching the `QueryDSL` schema.
- **Raises**: `ValidationError` if LLM output does not conform or fails validation after retry.

#### `compile_dsl(dsl: dict, metadata: MetaData) -> str`
Compiles valid DSL dictionary into SQL string.

- **Input**: Valid DSL dictionary, SQLAlchemy MetaData.
- **Output**: Executable SQL string.
- **Raises**: `DSLCompileError` for semantic issues (e.g. invalid column).

#### `run_nl2dsl(question: str) -> pd.DataFrame`
End-to-end execution.

- **Input**: Question.
- **Output**: Pandas DataFrame.
- **Behavior**: Orchestrates `generate` -> `compile` -> `execute`.
