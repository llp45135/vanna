# NL2DSL MVP 技术方案：JSON Schema + Pydantic + SQLAlchemy 实现详解

**文档目的**: 详细拆解 "定义 DSL Schema -> 开发编译器 -> 跑通单表闭环" 的技术实现细节。
**技术栈**: Python, Pydantic (Type Safety), SQLAlchemy Core (SQL Generation).

---

## 一、方案概览

核心思想是将 **"LLM 的输出"** 约束为 **"符合 Pydantic 定义的 JSON"**，然后通过 **"编译器"** 将其映射为 **"SQLAlchemy 的构建操作"**。

### 工作流
1.  **Define**: 用 Pydantic 定义 `QueryDSL` 类（作为协议）。
2.  **Generate**: LLM (Vanna) 输出 JSON。
3.  **Validate**: `QueryDSL.model_validate_json(json_str)` 进行校验。
4.  **Compile**: `Compiler.compile(query_dsl)` -> `SQLAlchemy Select` -> `Raw SQL`。

---

## 二、第一步：定义 DSL Schema (Pydantic)

我们需要一个**原子化、声明式**的数据结构。

```python
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator

# 1. 基础算子定义
class Filter(BaseModel):
    field: str = Field(..., description="数据库字段名或业务术语")
    op: Literal['eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'in', 'like'] = Field(..., description="操作符")
    value: Union[str, int, float, bool, List[str], List[int]] = Field(..., description="过滤值")

class Aggregation(BaseModel):
    func: Literal['sum', 'count', 'avg', 'min', 'max', 'count_distinct']
    field: str = Field(..., description="要聚合的字段，若为count(*)则填*")
    alias: Optional[str] = None

class Sort(BaseModel):
    field: str
    order: Literal['asc', 'desc'] = 'desc'

# 2. 顶层查询对象 (The Contract)
class QueryDSL(BaseModel):
    table: str = Field(..., description="目标表名")
    filters: List[Filter] = Field(default_factory=list)
    aggregates: List[Aggregation] = Field(default_factory=list)
    group_by: List[str] = Field(default_factory=list, description="分组字段列表")
    sorts: List[Sort] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=1000)

    @field_validator('group_by')
    def validate_group_by(cls, v, values):
        # 简单校验：如果有聚合，通常需要 Group By（除非是全表聚合）
        # 这里可以加更复杂的业务逻辑校验
        return v
```

### JSON 示例 (LLM 的目标输出)

```json
{
  "table": "orders",
  "filters": [
    {"field": "order_date", "op": "gte", "value": "2024-01-01"},
    {"field": "status", "op": "in", "value": ["completed", "shipped"]}
  ],
  "aggregates": [
    {"func": "sum", "field": "amount", "alias": "total_gmv"},
    {"func": "count_distinct", "field": "user_id", "alias": "uv"}
  ],
  "group_by": ["region"],
  "sorts": [{"field": "total_gmv", "order": "desc"}],
  "limit": 10
}
```

---

## 三、第二步：开发基础编译器 (SQLAlchemy Core)

编译器不拼接字符串，而是操作 `Table` 和 `Column` 对象。这天然防止了 SQL 注入。

### 3.1 环境准备
假设我们已经通过 Vanna 或其他方式获取了数据库的 `MetaData`。

```python
from sqlalchemy import Table, Column, MetaData, select, func, text, and_
from sqlalchemy.sql import Select

# 模拟元数据（实际项目中从 DB 反射加载）
metadata_obj = MetaData()
# 动态加载表定义 (Reflection)
# metadata_obj.reflect(bind=engine) 
```

### 3.2 编译器核心类

```python
class DSLCompiler:
    def __init__(self, metadata: MetaData):
        self.metadata = metadata

    def compile(self, dsl: QueryDSL) -> str:
        # 1. 获取表对象
        if dsl.table not in self.metadata.tables:
            raise ValueError(f"Table {dsl.table} not found in schema")
        
        table_obj = self.metadata.tables[dsl.table]
        
        # 2. 构建 Select 语句基础
        stmt = select()
        
        # 3. 处理 Columns / Aggregates (SELECT 部分)
        select_exprs = []
        
        # 处理 Group By 字段的投影
        for field in dsl.group_by:
            col = self._get_column(table_obj, field)
            select_exprs.append(col)
            
        # 处理聚合函数
        for agg in dsl.aggregates:
            col = self._get_column(table_obj, agg.field) if agg.field != "*" else text("*")
            
            if agg.func == 'sum':
                expr = func.sum(col)
            elif agg.func == 'count':
                expr = func.count(col)
            elif agg.func == 'count_distinct':
                expr = func.count(col.distinct())
            # ... 其他函数
            
            if agg.alias:
                expr = expr.label(agg.alias)
            select_exprs.append(expr)
            
        stmt = stmt.select_from(table_obj).with_only_columns(*select_exprs)

        # 4. 处理 Filters (WHERE 部分)
        where_clauses = []
        for f in dsl.filters:
            col = self._get_column(table_obj, f.field)
            val = f.value
            
            if f.op == 'eq': clause = (col == val)
            elif f.op == 'neq': clause = (col != val)
            elif f.op == 'gt': clause = (col > val)
            elif f.op == 'in': clause = col.in_(val)
            elif f.op == 'like': clause = col.like(val)
            # ... 其他操作符
            
            where_clauses.append(clause)
        
        if where_clauses:
            stmt = stmt.where(and_(*where_clauses))

        # 5. 处理 Group By
        if dsl.group_by:
            group_cols = [self._get_column(table_obj, f) for f in dsl.group_by]
            stmt = stmt.group_by(*group_cols)

        # 6. 处理 Sort (ORDER BY)
        for s in dsl.sorts:
            # 排序字段可能是聚合别名，也可能是原生列
            # 这里简化处理：先尝试按列名找
            if s.field in table_obj.columns:
                col = table_obj.columns[s.field]
            else:
                # 假如是别名，SQLAlchemy Core 通常能直接用字符串，或者需要引用 literal_column
                col = text(s.field) 
                
            if s.order == 'desc':
                stmt = stmt.order_by(col.desc())
            else:
                stmt = stmt.order_by(col.asc())

        # 7. Limit
        stmt = stmt.limit(dsl.limit)

        # 8. 编译为字符串 (方言适配)
        # 这里的 compile 会根据绑定的 engine 自动处理方言（如 Postgres vs MySQL 的引号区别）
        return str(stmt.compile(compile_kwargs={"literal_binds": True}))

    def _get_column(self, table: Table, field_name: str):
        """简单的列名查找，这里是未来做'业务术语映射'的扩展点"""
        if field_name == "*": return "*"
        if field_name not in table.columns:
            raise ValueError(f"Column {field_name} not found in table {table.name}")
        return table.columns[field_name]
```

---

## 四、第三步：跑通单表闭环 (Integration)

将 Vanna 与上述组件串联。

### 1. 改造 Vanna 的 Prompt
我们需要覆盖 `vn.generate_sql` 的逻辑，或者创建一个新的方法 `vn.generate_dsl`。

```python
SYSTEM_PROMPT = """
你是一个数据分析助手。请将用户的自然语言查询转换为以下 JSON 格式。
不要输出 SQL，只输出 JSON。

Schema 定义:
{
  "filters": [{"field": "字段名", "op": "eq/gt/lt/in", "value": "值"}],
  "aggregates": [{"func": "sum/count", "field": "字段名", "alias": "别名"}],
  ...
}

表结构信息:
{ddl}

用户输入: {question}
"""
```

### 2. 闭环执行代码
```python
def run_nl2dsl_pipeline(vn, question: str):
    # 1. 检索上下文 (Vanna 原生能力)
    related_ddl = vn.get_related_ddl(question)
    
    # 2. 调用 LLM 生成 JSON
    prompt = SYSTEM_PROMPT.format(ddl=related_ddl, question=question)
    llm_response = vn.llm_service.chat(prompt) # 伪代码，调用 LLM
    
    # 3. Pydantic 校验 (关键步骤：防幻觉)
    try:
        dsl_obj = QueryDSL.model_validate_json(llm_response)
    except Exception as e:
        print(f"DSL 格式错误: {e}")
        # 这里可以做 Self-Correction: 把错误扔回给 LLM 让它重修
        return
        
    # 4. 编译器转译
    compiler = DSLCompiler(vn.metadata) # 假设 vn 已绑定 metadata
    try:
        sql = compiler.compile(dsl_obj)
    except ValueError as e:
        print(f"语义错误: {e}") # 比如字段不存在
        return

    # 5. 执行 SQL
    print(f"Generated SQL: {sql}")
    df = vn.run_sql(sql)
    return df
```

---

## 五、总结与扩展点

通过这套 **"JSON Schema + Pydantic + SQLAlchemy"** 组合拳，我们实现了：

1.  **强类型约束**: Pydantic 保证了 LLM 输出的结构绝对正确，缺字段、类型不对都会直接报错（而不是执行时报错）。
2.  **SQL 安全**: SQLAlchemy Core 构建 AST，杜绝了拼接字符串带来的注入风险。
3.  **方言无关**: SQLAlchemy 一次编写，可编译为 PG, MySQL, Oracle 等多种方言。

### 后续扩展方向 (P2 阶段)
*   **语义映射**: 在 `_get_column` 方法中加入字典查找，实现 "销售额" -> `sale_amount` 的映射。
*   **跨表 Join**: `DSLCompiler` 升级，支持传入 `Graph` 对象，根据 `table` 自动计算 Join Path。
*   **权限控制**: 在 `compile` 方法入口处，根据当前 user 注入 `filters.append({...})`。
