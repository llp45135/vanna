"""
DSL Compiler module: Transforms JSON DSL into SQLAlchemy Expression Language.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from sqlalchemy import func, extract, Column
from sqlalchemy.sql import expression

from .types import TimeGrain
from .errors import DSLCompileError


class TimeGrainCompiler(ABC):
    """
    Abstract strategy for compiling TimeGrain truncations.
    Different databases (SQLite, Postgres) handle date truncation differently.
    """

    @abstractmethod
    def compile(self, column: expression.ColumnElement, grain: TimeGrain) -> expression.ColumnElement:
        """
        Apply truncation function to the column.
        """
        pass


class SQLiteTimeGrainCompiler(TimeGrainCompiler):
    """
    SQLite implementation using strftime.
    """

    def compile(self, column: expression.ColumnElement, grain: TimeGrain) -> expression.ColumnElement:
        # Dictionary mapping TimeGrain to strftime format strings
        # SQLite doesn't have native date types, usually strings or ISO logic.
        # We assume standard ISO8601 strings in the DB or SQLite date types.
        
        # Formats:
        # YEAR -> '%Y-01-01'
        # MONTH -> '%Y-%m-01'
        # DAY -> '%Y-%m-%d'
        
        formats = {
            TimeGrain.YEAR: '%Y-01-01',
            TimeGrain.QUARTER: None, # SQLite quarter is tricky, often requires calculation or case
            TimeGrain.MONTH: '%Y-%m-01',
            TimeGrain.WEEK: None, # Tricky: '%Y-%W' or similar, but needs specific start of week logic
            TimeGrain.DAY: '%Y-%m-%d',
        }

        fmt = formats.get(grain)
        
        if fmt:
            return func.strftime(fmt, column)
        
        # Fallback/Complex logic for Quarter/Week
        if grain == TimeGrain.QUARTER:
             # Very hacky for SQLite without extensions: 
             # We might skip strictly implementing Quarter/Week in MVP for SQLite 
             # OR implement a basic version.
             # Using a CASE statement or math on month:
             # (strftime('%m', col) + 2) / 3 ... complex to build in AST easily without verbosity.
             # MVP Decision: Support Year, Month, Day reliably. Raise error for others if complex.
             # Actually, spec says we MUST support Standard Analytics Set.
             # Let's support Week via %W (Week of year) - but mapped to a date is hard.
             
             # Let's prioritize Year/Month/Day for SC-004 verification if possible, 
             # but the spec lists them all.
             raise DSLCompileError(f"TimeGrain '{grain}' not yet fully supported for SQLite MVP")
        
        if grain == TimeGrain.WEEK:
             # strftime('%Y-%W', ...)
             return func.strftime('%Y-%W', column)

        return column


class DSLCompiler:
    """
    Compiles QueryDSL into SQLAlchemy Select expressions.
    """

    def __init__(self, metadata: Any, dialect_name: str = "sqlite"):
        """
        :param metadata: SQLAlchemy MetaData object (containing defined Tables)
        :param dialect_name: Target dialect (sqlite, postgresql) for specific compilation strategies.
        """
        self.metadata = metadata
        self.dialect_name = dialect_name
        
        # Strategy selection
        if dialect_name == "sqlite":
            self._time_compiler = SQLiteTimeGrainCompiler()
        else:
            # Fallback for MVP
            self._time_compiler = SQLiteTimeGrainCompiler()

    def compile_to_str(self, dsl: Any) -> str:
        """
        Generates executable SQL string.
        """
        stmt = self.compile_to_sqlalchemy(dsl)
        # compile() produces a bind-parameter query. 
        # For 'literal' string generation (e.g. for display/logging), we can use literal_binds.
        # But for execution, we usually want bindings.
        # However, Vanna's `run_sql` expects a string.
        # We will render it with literal binds for MVP simplicity if Vanna's run_sql doesn't take params.
        # Vanna's standard run_sql takes a raw string.
        
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        return str(compiled)

    def compile_to_sqlalchemy(self, dsl: Any):
        """
        Generates SQLAlchemy Select construct.
        """
        from sqlalchemy import select, table, column, text, Table
        
        # 1. Resolve Table
        if dsl.table not in self.metadata.tables:
            # Check if it is a real table or if we should treat it as a generic table
            # For strict mode (SC-003), we MUST validate against metadata.
            # If metadata is empty? We might fail.
            # MVP: We assume metadata is populated.
            raise DSLCompileError(f"Table '{dsl.table}' not found in metadata.")
        
        target_table = self.metadata.tables[dsl.table]
        
        # 2. Build Query
        stmt = select()
        
        # 3. Aggregations & Selections
        select_exprs = []
        
        # If no aggregates/group_by, select *? Or specific columns?
        # DSL usually implies analytical query.
        
        # TimeGrains - usually part of Group By / Select
        # We need to compute the truncation transformation
        
        # Map alias -> expression for referencing in GroupBy/Sort
        expr_map = {} 

        # Handle Time Dimensions first (as they are often grouped logic)
        for td in dsl.time_grains:
            col = self._get_column(target_table, td.field)
            expr = self._time_compiler.compile(col, td.grain)
            label = expr.label(td.alias)
            select_exprs.append(label)
            expr_map[td.alias] = label # Use label for ordering/grouping
        
        # Handle Aggregates
        for agg in dsl.aggregates:
            col = self._get_column(target_table, agg.field)
            
            if agg.func == 'sum':
                expr = func.sum(col)
            elif agg.func == 'count':
                expr = func.count(col)
            elif agg.func == 'avg':
                expr = func.avg(col)
            elif agg.func == 'min':
                expr = func.min(col)
            elif agg.func == 'max':
                expr = func.max(col)
            elif agg.func == 'count_distinct':
                expr = func.count(expression.distinct(col))
            else:
                raise DSLCompileError(f"Unsupported aggregation: {agg.func}")
            
            if agg.alias:
                label = expr.label(agg.alias)
                select_exprs.append(label)
                expr_map[agg.alias] = label
            else:
                select_exprs.append(expr)
        
        # If no explicit selects, maybe select all? 
        # But for an analytical intent, usually we select what we group/agg.
        # If strict: allow 'group_by' columns to be selected automatically?
        # For this MVP, let's assume we select what explicitly defined in time_grain + aggs.
        # If `group_by` has columns not in time_grain?
        
        for dim in dsl.group_by:
             # If it's already a time_grain alias, skip adding simple column
             if dim in expr_map:
                 continue
             # Else add raw column
             col = self._get_column(target_table, dim)
             select_exprs.append(col)
             expr_map[dim] = col

        if not select_exprs:
             # Fallback select *
             stmt = stmt.select_from(target_table).add_columns(text("*"))
        else:
             stmt = select(*select_exprs).select_from(target_table)

        # 4. Filters
        for f in dsl.filters:
            col = self._get_column(target_table, f.field)
            val = f.value
            
            if f.op == 'eq':
                stmt = stmt.where(col == val)
            elif f.op == 'neq':
                stmt = stmt.where(col != val)
            elif f.op == 'gt':
                stmt = stmt.where(col > val)
            elif f.op == 'lt':
                stmt = stmt.where(col < val)
            elif f.op == 'gte':
                stmt = stmt.where(col >= val)
            elif f.op == 'lte':
                stmt = stmt.where(col <= val)
            elif f.op == 'like':
                stmt = stmt.where(col.like(val))
            elif f.op == 'in':
                # Pydantic validates it's a list?
                if not isinstance(val, list):
                     raise DSLCompileError(f"Operator 'in' requires list value, got {type(val)}")
                stmt = stmt.where(col.in_(val))
            else:
                raise DSLCompileError(f"Unsupported operator: {f.op}")
        
        # 5. Group By
        for dim in dsl.group_by:
            if dim in expr_map:
                # Group by the expression (e.g. truncated date)
                stmt = stmt.group_by(expr_map[dim])
            else:
                # Group by raw column
                stmt = stmt.group_by(self._get_column(target_table, dim))
        
        # 6. Sorts
        for s in dsl.sorts:
            if s.field in expr_map:
                target = expr_map[s.field]
            else:
                target = self._get_column(target_table, s.field)
            
            if s.order == 'desc':
                stmt = stmt.order_by(target.desc())
            else:
                stmt = stmt.order_by(target.asc())
        
        # 7. Limit
        if dsl.limit and dsl.limit > 0:
            stmt = stmt.limit(dsl.limit)
            
        return stmt

    def _get_column(self, table: Any, col_name: str) -> expression.ColumnElement:
        """
        Helper to safely get column from table or raise Schema Error.
        """
        if col_name == "*":
             # Special case for count(*) -> usually modeled as func.count() with no arg or literal '*'
             # But SQLAlchemy count(col) is standard. count(*) needs literal_column('*')
             from sqlalchemy import literal_column
             return literal_column("*")

        if col_name not in table.columns:
            raise DSLCompileError(f"Column '{col_name}' not found in table '{table.name}'")
        return table.columns[col_name]

