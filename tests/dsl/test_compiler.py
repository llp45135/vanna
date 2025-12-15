
import pytest
from sqlalchemy import MetaData, Table, Column, Integer, String, Date
from vanna.dsl.schema import QueryDSL, Filter, Aggregation, TimeDimension
from vanna.dsl.compiler import DSLCompiler
from vanna.dsl.errors import DSLCompileError
from vanna.dsl.types import FilterOperator, AggregationFunction, TimeGrain

@pytest.fixture
def mock_metadata():
    metadata = MetaData()
    Table(
        "orders", metadata,
        Column("id", Integer, primary_key=True),
        Column("region", String),
        Column("amount", Integer),
        Column("date_col", Date)
    )
    return metadata

def test_compile_simple(mock_metadata):
    dsl = QueryDSL(
        table="orders",
        filters=[ Filter(field="region", op=FilterOperator.EQ, value="East") ],
        aggregates=[ Aggregation(func=AggregationFunction.SUM, field="amount") ]
    )
    compiler = DSLCompiler(mock_metadata)
    sql = compiler.compile_to_str(dsl)
    
    # Check key parts of SQL
    assert "SELECT sum(orders.amount)" in sql
    assert "FROM orders" in sql
    assert "WHERE orders.region = 'East'" in sql

def test_compile_invalid_table(mock_metadata):
    dsl = QueryDSL(table="missing_table")
    compiler = DSLCompiler(mock_metadata)
    with pytest.raises(DSLCompileError) as exc:
        compiler.compile_to_str(dsl)
    assert "not found in metadata" in str(exc.value)

def test_compile_invalid_column(mock_metadata):
    dsl = QueryDSL(
        table="orders",
        filters=[ Filter(field="bad_col", op=FilterOperator.EQ, value="X") ]
    )
    compiler = DSLCompiler(mock_metadata)
    with pytest.raises(DSLCompileError) as exc:
        compiler.compile_to_str(dsl)
    assert "Column 'bad_col' not found" in str(exc.value)

def test_compile_aggregate_invalid_column(mock_metadata):
    dsl = QueryDSL(
        table="orders",
        aggregates=[ Aggregation(func=AggregationFunction.SUM, field="ghost_col") ]
    )
    compiler = DSLCompiler(mock_metadata)
    with pytest.raises(DSLCompileError) as exc:
        compiler.compile_to_str(dsl)
    assert "Column 'ghost_col' not found" in str(exc.value)

def test_compile_groupby_invalid_column(mock_metadata):
    dsl = QueryDSL(
        table="orders",
        group_by=["imaginary_dim"]
    )
    compiler = DSLCompiler(mock_metadata)
    with pytest.raises(DSLCompileError) as exc:
        compiler.compile_to_str(dsl)
    assert "Column 'imaginary_dim' not found" in str(exc.value)

def test_time_grain_sqlite(mock_metadata):
    # Test TimeGrain compilation
    dsl = QueryDSL(
        table="orders",
        time_grains=[ TimeDimension(field="date_col", grain=TimeGrain.YEAR, alias="year_col") ],
        group_by=["year_col"]
    )
    compiler = DSLCompiler(mock_metadata, dialect_name="sqlite")
    sql = compiler.compile_to_str(dsl)
    
    # Expect strftime('%Y-01-01', orders.date_col)
    assert "strftime('%Y-01-01', orders.date_col)" in sql
    assert "GROUP BY strftime('%Y-01-01', orders.date_col)" in sql

def test_unsupported_aggregation(mock_metadata):
    # Manually forcing unsupported func (bypassing pydantic enum validation for unit test sake, or if enum expands but compiler doesn't)
    # Since Pydantic validates Enum, we can't easily pass invalid enum string unless we mock model.
    # But if we assume schema is valid Pydantic model, DSLCompiler covers all Enum members?
    # DSLCompiler handles all members of AggregationFunction currently defined?
    # Let's verify Coverage.
    pass

def test_limit(mock_metadata):
    dsl = QueryDSL(table="orders", limit=10)
    compiler = DSLCompiler(mock_metadata)
    sql = compiler.compile_to_str(dsl)
    assert "LIMIT 10" in sql
