# Quickstart: NL2DSL MVP

**Prerequisites**: Vanna installed with `nl2dsl` feature.

## 1. Setup

```python
import vanna
from vanna.remote import VannaDefault

# Initialize Vanna (as usual)
vn = VannaDefault(model='...', api_key='...')

# Connect to Database (SQLAlchemy)
vn.connect_to_sqlite('TicketDB/ticket.db')
```

## 2. Using NL2DSL

The new NL2DSL flow is available via `run_nl2dsl`.

```python
# 1. Ask a question
question = "What is the total sales by year?"

# 2. Run with Semantic Layer
# This uses the intermediate DSL to ensure the SQL is structurally correct.
df = vn.run_nl2dsl(question)

print(df)
```

## 3. Debugging / Inspection

You can inspect the intermediate steps:

```python
# View the generated DSL
dsl = vn.generate_dsl(question)
print("Generated DSL:", dsl)

# View the compiled SQL
sql = vn.compile_dsl(dsl)
print("Compiled SQL:", sql)
```
