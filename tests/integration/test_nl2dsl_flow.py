
import pytest
import pandas as pd
from sqlalchemy import create_engine, text
from vanna.core.nl2dsl import NL2DSLMixin

# Mock class simulating Vanna setup
class MockVanna(NL2DSLMixin):
    def __init__(self, engine):
        self._engine = engine
        self.run_sql_is_set = True

    def submit_prompt(self, prompt, **kwargs):
        # Mock LLM response: Correct JSON DSL for "Total sales"
        # We simulate the LLM outputting the exact string needed.
        return """
        ```json
        {
            "table": "sales",
            "aggregates": [
                {"func": "sum", "field": "amount", "alias": "total_sales"}
            ],
            "filters": [
                {"field": "region", "op": "eq", "value": "East"}
            ],
            "group_by": [],
            "time_grains": [],
            "sorts": [],
            "limit": 10
        }
        ```
        """

    def get_related_training_data(self, question, **kwargs):
        return {"ddl": ["CREATE TABLE sales (id INTEGER, amount INTEGER, region TEXT)"]}

    def run_sql(self, sql, **kwargs):
        return pd.read_sql(sql, self._engine)
        
    @property
    def engine(self):
        return self._engine

@pytest.fixture
def loaded_engine():
    # In-memory SQLite
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE sales (id INTEGER, amount INTEGER, region TEXT)"))
        conn.execute(text("INSERT INTO sales (id, amount, region) VALUES (1, 100, 'East')"))
        conn.execute(text("INSERT INTO sales (id, amount, region) VALUES (2, 200, 'West')"))
        conn.execute(text("INSERT INTO sales (id, amount, region) VALUES (3, 300, 'East')"))
        conn.commit()
    return engine

def test_nl2dsl_flow_happy_path(loaded_engine):
    vn = MockVanna(loaded_engine)
    
    # 1. Ask question
    df = vn.run_nl2dsl("What are the total sales in East region?")
    
    # 2. Verify Result
    # DSL should filter Region=East (100+300 = 400)
    assert not df.empty
    assert "total_sales" in df.columns
    # SQLite often returns aggregation, length 1
    assert len(df) == 1
    assert df.iloc[0]['total_sales'] == 400

def test_nl2dsl_schema_error_retry_logic():
    # Advanced: Test that if LLM returns invalid JSON first, we retry.
    pass
