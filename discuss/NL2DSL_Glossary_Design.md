# NL2DSL 语义层设计：商业术语与行业黑话的 DSL 关联

> **版本**: 1.0 | **状态**: 草案 | **日期**: 2025-12-15

---

## 1. 背景与问题陈述

### 1.1 业务场景

在企业数据分析场景中，业务用户（分析师、运营、产品经理）日常使用大量的**行业术语**和**企业内部黑话**来描述其数据需求。例如：

- **"大鲸鱼用户"**（Whale Users）：高消费、高价值客户的俗称。
- **"掉单"**：电商领域指支付失败，物流领域指包裹丢失。
- **"ARPU"**：Average Revenue Per User，用户平均贡献收入。
- **"ROI"**：Return on Investment，投资回报率。

这些术语在日常沟通中高频出现，但其背后的**精确数据定义**往往是模糊的、隐性的，甚至在不同团队间存在分歧。

### 1.2 核心痛点

当前，将这些业务术语转化为可执行的数据查询存在以下关键挑战：

| 痛点 | 描述 | 影响 |
| :--- | :--- | :--- |
| **定义模糊** | "高价值用户" 是指消费金额高，还是活跃度高，还是两者兼具？ | 查询结果不一致，决策失真 |
| **上下文缺失** | LLM 通用知识无法覆盖企业特定的业务逻辑和数据模型 | 生成的 SQL 语义错误 |
| **复杂计算** | `ROI = (sum(revenue) - sum(cost)) / sum(cost)` 涉及多字段组合计算 | 当前 DSL 原子聚合无法直接表达 |
| **维护成本高** | 传统方式依赖硬编码 SQL 视图或 ETL，每次变更需工程师介入 | 业务敏捷性受阻 |

### 1.3 传统解决方案的局限性

在 LLM 出现之前，企业通常采用以下方式处理术语映射：

1.  **数据库视图 (Views)**：DBA 根据业务需求创建 `view_high_value_users`。
    - *缺点*：需精确匹配表名/视图名，无法处理同义词或模糊表达。
2.  **ETL 管道**：在数据仓库中预先计算派生指标（如 ROI）并存入物理表。
    - *缺点*：计算逻辑固化，变更需修改代码并重新跑批。
3.  **BI 工具的语义层**（如 Looker LookML、dbt Semantic Layer）：
    - *缺点*：需要专业人员维护，学习曲线陡峭，与自然语言交互能力有限。

**核心问题**：所有这些方案都要求用户使用**预定义的精确名称**进行查询，无法处理自然语言的**模糊性**和**多样性**。

---

## 2. 现有成果与技术基础

本设计建立在 **NL2DSL MVP** 已完成的技术成果之上。

### 2.1 NL2DSL MVP 核心能力

| 能力 | 描述 | 评估结果 |
| :--- | :--- | :--- |
| **自然语言转 DSL** | 将用户问题转换为结构化的 `QueryDSL` JSON | 准确率 **95%** |
| **DSL 编译** | 将 `QueryDSL` 编译为目标数据库的 SQL | 语法正确率 **100%** |
| **RAG 上下文注入** | 通过向量检索将 DDL、文档等注入 Prompt | 已实现 |
| **Pydantic 模式验证** | 确保 LLM 输出符合 DSL Schema | 已实现 |

### 2.2 当前 DSL Schema 结构

```python
class QueryDSL(BaseModel):
    table: str
    filters: List[Filter]        # 过滤条件
    aggregates: List[Aggregation] # 原子聚合 (sum, count, avg, min, max)
    group_by: List[str]          # 分组维度
    time_grains: List[TimeDimension]
    sorts: List[Sort]
    limit: Optional[int]
```

### 2.3 技术基础设施

- **向量数据库**：ChromaDB，用于存储和检索 DDL、文档、示例。
- **LLM 服务**：支持 OpenAI 兼容 API（本地或云端）。
- **训练 API**：`vn.train(ddl=..., documentation=..., sql=...)` 用于知识沉淀。

---

## 3. 解决方案：语义词汇层 (Semantic Glossary Layer)

### 3.1 设计目标

在不侵入 DSL 编译器核心逻辑的前提下，通过扩展 **RAG 上下文** 来支持商业术语的**动态映射**。

### 3.2 核心数据结构

引入 `GlossaryItem` 存储于向量数据库：

```python
class GlossaryItem(BaseModel):
    term: str          # 术语名称，如 "Whale User"
    definition: str    # 自然语言定义，如 "Users with lifetime spend > $1000"
    dsl_fragment: Optional[dict]  # 可选的 DSL 片段
    tags: List[str]    # 行业/项目标签
```

### 3.3 工作流程

```
┌─────────────────────────────────────────────────────────────────────┐
│  用户提问: "Show me the churn rate of whale users"                   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  术语检索 (Semantic Search)                                          │
│  ─────────────────────────────────                                  │
│  • "churn rate" → Definition: inactive 30 days / total users        │
│  • "whale users" → Definition: lifetime spend > 1000                │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Prompt 构建                                                         │
│  ─────────────────────────────────                                  │
│  ===Tables                                                          │
│  CREATE TABLE users (id, name, total_spend, last_active_date, ...)  │
│                                                                     │
│  ===Project Glossary                                                │
│  1. "Whale Users": Users with total_spend > 1000                    │
│  2. "Churn Rate": count(inactive 30 days) / count(all users)        │
│                                                                     │
│  ===Question                                                        │
│  Show me the churn rate of whale users                              │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LLM 生成 DSL                                                        │
│  ─────────────────────────────────                                  │
│  {                                                                  │
│    "table": "users",                                                │
│    "filters": [{"field": "total_spend", "op": "gt", "value": 1000}],│
│    "aggregates": [                                                  │
│      {"expression": "COUNT(CASE WHEN ...) / COUNT(*)", "alias": ...}│
│    ]                                                                │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.4 支持的术语类型

| 类型 | 示例 | DSL 映射方式 |
| :--- | :--- | :--- |
| **命名过滤器** | "High Value Users" | `filters: [{field: spend, op: gt, value: 1000}]` |
| **派生指标** | "AOV", "ROI" | `aggregates: [{expression: "SUM(x)/COUNT(y)"}]` |
| **实体同义词** | "Client" = "Customer" = "users 表" | `table: "users"` |

### 3.5 DSL Schema 扩展：Expression 字段

为支持复合计算指标，扩展 `Aggregation` 模型：

```python
class Aggregation(BaseModel):
    func: Optional[AggregationFunction] = None
    field: Optional[str] = None
    expression: Optional[str] = None  # ← 新增：原生 SQL 表达式
    alias: str
```

这允许 LLM 直接输出如 `SUM(revenue) / COUNT(order_id)` 的表达式，由数据库计算最终结果。

### 3.6 API 扩展

扩展 `train()` 方法支持术语训练：

```python
vn.train(glossary={
    "term": "High Value Transactions",
    "definition": "Transactions with amount > 1000 USD"
})
```

---

## 4. 价值与优势

| 维度 | 传统方式 | 本方案 |
| :--- | :--- | :--- |
| **映射能力** | 精确匹配 | 语义模糊匹配 |
| **维护成本** | 需工程师修改代码/SQL | 业务人员修改文本定义 |
| **变更生效** | 需部署 | 即时生效 |
| **扩展性** | 每个术语需单独建视图 | 向量库自动扩展 |

---

## 5. 协作模式：数据治理前提

本方案的成功实施依赖于**领域专家**与**开发人员**的紧密协作：

| 角色 | 职责 |
| :--- | :--- |
| **领域专家** | 定义业务术语的精确含义（"What"） |
| **开发人员** | 将定义转化为 DSL/SQL 表达式（"How"） |
| **数据治理** | 确保术语库的唯一性和一致性（"Single Source of Truth"） |

> **核心认知**：代码只是容器，真正的价值在于共同沉淀的**知识库**。

---

## 6. 实施计划

1.  **P0**：实现 `vn.train(glossary=...)` API
2.  **P0**：修改 `NL2DSLMixin.generate_dsl()` 检索并注入 Glossary
3.  **P1**：扩展 `Aggregation` 支持 `expression` 字段
4.  **P1**：创建包含行业术语的 Golden Set 进行验证
5.  **P2**：开发 Glossary 管理 UI（可视化维护术语库）

---

## 7. 附录：参考资料

- [NL2DSL MVP 技术设计](NL2DSL_MVP_Technical_Design.md)
- [NL2DSL MVP 评估报告](NL2DSL_MVP_Evaluation_Report.md)
- [DSL Schema 定义](../src/vanna/dsl/schema.py)
