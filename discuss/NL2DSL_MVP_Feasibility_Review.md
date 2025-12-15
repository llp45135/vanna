# NL2DSL MVP 技术方案可行性与风险评审

**日期**: 2025-12-15
**评审对象**: [`discuss/NL2DSL_MVP_Technical_Design.md`](file:///Users/LLP/opensource/vanna/discuss/NL2DSL_MVP_Technical_Design.md)

---

## 一、总体可行性评估

### ✅ 技术可行性: **高**

方案选择的技术栈成熟稳定，核心组件均有广泛的生产级应用案例：

| 组件 | 评估 | 说明 |
| :--- | :---: | :--- |
| **Pydantic** | ✅ 成熟 | Python 社区事实标准，FastAPI 等框架的基础。`model_validate_json` 性能优秀。 |
| **SQLAlchemy Core** | ✅ 成熟 | 业界标准 ORM，Core 层 (非 ORM 层) 直接构建 AST，轻量高效。 |
| **LLM JSON Mode** | ✅ 成熟 | OpenAI/Anthropic/Gemini 等主流 LLM 均支持 `response_format: json_object` 或 Function Calling。 |
| **Vanna Context Retrieval** | ✅ 原生支持 | 直接复用 `vn.get_related_ddl()`，无需额外开发。 |

---

## 二、技术风险识别

### 2.1 🔴 关键风险 (High)

#### R1: LLM JSON 输出稳定性
*   **问题**: 尽管 LLM 支持 JSON Mode，但复杂查询时仍可能出现格式错误（如缺少引号、嵌套过深、幻觉字段名）。
*   **影响**: `QueryDSL.model_validate_json()` 抛出 `ValidationError`，用户请求失败。
*   **缓解措施**:
    1.  **Few-Shot Prompting**: 在 System Prompt 中提供 3-5 个标准 Q&A 示例。
    2.  **Self-Correction Loop**: 捕获 `ValidationError`，将错误信息结构化后反馈给 LLM，要求其修正并重新生成。最多重试 2 次。
    3.  **Fallback**: 超过重试次数后，返回友好提示而非崩溃。

#### R2: 字段名/表名不存在
*   **问题**: LLM 可能生成实际 Schema 中不存在的字段名（幻觉）。当前 `_get_column` 只会抛 `ValueError`。
*   **影响**: 编译失败，用户体验差。
*   **缓解措施**:
    1.  **Prompt 强化**: 在 DDL 上下文中显式列出**所有可用字段名**（白名单）。
    2.  **Fuzzy Matching**: 如果 `field` 不存在，尝试用 Levenshtein 距离找最接近的列名，并提示 "您是指 xxx 吗？"
    3.  **语义映射层**: P2 阶段引入 Glossary，将业务术语映射到物理列名。

### 2.2 🟡 中等风险 (Medium)

#### R3: DSL 表达力边界
*   **问题**: 当前 DSL 仅支持 `Filter`, `Aggregation`, `Sort`, `Limit`。无法表达：
    *   **窗口函数**: `ROW_NUMBER()`, `LAG()`, `LEAD()`
    *   **HAVING 子句**: 对聚合结果再过滤
    *   **子查询/CTE**: 复杂的嵌套逻辑
*   **影响**: 用户遇到复杂需求时系统无法满足，被迫绕行或放弃。
*   **缓解措施**:
    1.  **MVP 范围明确**: 文档中应明确声明 "MVP 仅支持单表简单聚合"。
    2.  **逐步扩展**: 在 DSL 中预留 `advanced_filters` 或 `raw_expression` 字段作为逃生舱。
    3.  **覆盖率验证**: 实施前用 Top 50 历史 SQL 做覆盖率测试，确保 MVP 能处理 >=70% 的高频查询。

#### R4: ORDER BY 别名处理
*   **问题**: 代码中 `sorts` 字段可能引用聚合的 `alias`（如 `total_gmv`），但 SQLAlchemy 直接用 `text(s.field)` 存在 SQL 注入隐患。
*   **缓解措施**:
    1.  编译器内部维护一个 `alias_registry: Dict[str, ColumnElement]`，在处理聚合时记录。
    2.  `sorts` 阶段先查 `alias_registry`，找不到才去 `table.columns`，**禁止使用 `text()`**。

### 2.3 🟢 低风险 (Low)

#### R5: SQLAlchemy 方言适配
*   **问题**: `stmt.compile()` 默认不绑定方言，可能生成通用 SQL 而非目标数据库特定语法。
*   **缓解措施**: 在 `DSLCompiler.__init__` 接收 `dialect` 参数（如 `postgresql`），并在 `compile` 时传入 `dialect=postgresql.dialect()`。

---

## 三、实施步骤细化

### Phase 1: 基础架构 (Week 1)

| 步骤 | 任务 | 验收标准 |
| :---: | :--- | :--- |
| 1.1 | 创建 `src/vanna/semantic/` 目录结构 | 目录存在，包含 `__init__.py` |
| 1.2 | 实现 `dsl_schema.py` (Pydantic Models) | 单元测试：`QueryDSL.model_validate_json(sample_json)` 通过 |
| 1.3 | 实现 `compiler.py` (DSLCompiler 类) | 单元测试：给定固定 DSL，输出符合预期的 SQL |
| 1.4 | 编写 `tests/test_dsl_compiler.py` | 测试覆盖率 >= 80% |

### Phase 2: Vanna 集成 (Week 2)

| 步骤 | 任务 | 验收标准 |
| :---: | :--- | :--- |
| 2.1 | 设计 `generate_dsl` Prompt 模板 | LLM 在 10 个标准问题上 JSON 格式正确率 >= 90% |
| 2.2 | 实现 `run_nl2dsl_pipeline` 函数 | 集成测试：`pipeline("查询订单总额 by region")` 返回 DataFrame |
| 2.3 | 实现 Self-Correction Loop | 模拟 `ValidationError`，验证重试逻辑 |
| 2.4 | 编写 Notebook 演示 | 提供 `notebooks/nl2dsl_demo.ipynb` |

### Phase 3: 验证与文档 (Week 3-4)

| 步骤 | 任务 | 验收标准 |
| :---: | :--- | :--- |
| 3.1 | 历史 SQL 覆盖率测试 | 抽取 50 条历史 SQL，DSL 化成功率 >= 70% |
| 3.2 | 性能基准测试 | DSL 编译延迟 < 10ms (P99) |
| 3.3 | 编写 `USAGE.md` 使用文档 | 包含 QuickStart 和 FAQ |
| 3.4 | 内部 Demo 与反馈收集 | 至少 3 名内部用户试用并提交反馈 |

---

## 四、代码层面的具体建议

### 4.1 增强 `QueryDSL` 校验

```python
from pydantic import model_validator

class QueryDSL(BaseModel):
    # ... 原有字段 ...

    @model_validator(mode='after')
    def check_aggregation_groupby_consistency(self):
        """如果有聚合函数，则必须有 group_by 或全表聚合（空 group_by）"""
        if self.aggregates and not self.group_by:
            # 允许全表聚合 (类似 SELECT COUNT(*) FROM ...)
            pass
        return self
```

### 4.2 安全的 ORDER BY 处理

```python
class DSLCompiler:
    def compile(self, dsl: QueryDSL) -> str:
        # ... 前置代码 ...

        # 创建别名注册表
        alias_registry = {}

        for agg in dsl.aggregates:
            # ... 原有聚合处理 ...
            if agg.alias:
                alias_registry[agg.alias] = expr

        # 安全的 ORDER BY
        for s in dsl.sorts:
            if s.field in alias_registry:
                col = alias_registry[s.field]
            elif s.field in table_obj.columns:
                col = table_obj.columns[s.field]
            else:
                raise ValueError(f"Unknown sort field: {s.field}")

            # ... 排序逻辑 ...
```

---

## 五、结论

*   **整体可行**: 技术选型合理，MVP 范围明确，风险可控。
*   **关键行动**:
    1.  在编码前完成 **历史 SQL 覆盖率预测试**，确保 DSL 表达力足够。
    2.  实现 **Self-Correction Loop**，这是 LLM 输出稳定性的核心保障。
    3.  **严禁使用 `text()` 拼接用户输入**，所有字段必须经过白名单校验。
