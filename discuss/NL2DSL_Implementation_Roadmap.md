# NL2DSL 深度实现路线图：打造可信 AI 数据平台

本文档详细拆解如何从零构建 **NL2DSL (Natural Language to Domain Specific Language)** 架构，实现 "可信、安全、可治理" 的 AI 数据分析平台。

---

## 阶段一：核心定义与 MVP (Week 1-4)

**目标**：跑通 `Natural Language -> JSON DSL -> SQL -> Result` 的最小闭环。

### 1.1 定义 DSL Schema (The Trust Contract)
不仅仅是 JSON，而是严格定义的 **JSON Schema**。这是 AI 与 Compiler 之间的契约。
*   **设计原则**: 声明式 (Declarative)、原子化 (Atomic)、与方言无关 (Dialect-Agnostic)。
*   **核心算子**:
    *   `Source`: 定义数据源 (Table / View / Sub-query)。
    *   `Filter`: 逻辑谓词 (AND, OR, >, <, IN)。
    *   `Aggregation`: 聚合操作 (SUM, COUNT, COUNT_DISTINCT)。
    *   `Breakdown`: 分组维度 (GROUP BY)。
    *   `TimeGrain`: 时间粒度 (Daily, Weekly, Monthly)。

### 1.2 构建基础 Compiler (Python)
编写一个 Python 模块，将上述 JSON 翻译为标准 SQL。
*   **技术选型**: 建议使用 `SQLAlchemy Core` 或 `Pypika` 作为 AST Builder，**严禁使用字符串拼接**。
*   **功能**:
    *   解析 JSON DSL。
    *   映射 DSL 字段名 -> 真实 DB 列名 (`vanna.get_related_ddl` 的升级版)。
    *   生成基础 SQL (SELECT ... FROM ... WHERE ... GROUP BY ...)。

### 1.3 改造 Vanna Prompt
*   不让 Vanna 直接写 SQL。
*   Few-Shot Prompting: 输入自然语言，输出符合 Schema 的 JSON。
*   增加 `Validator` 环节：Vanna 生成 JSON 后，先用 Pydantic 校验，通不过则由于 Compiler 报错并反馈给 Vanna 重试。

---

## 阶段二：语义层与指标库 (Week 5-8)

**目标**：解决 "一致性" 问题，消除 "幻觉"。

### 2.1 打造 Metrics Store (指标的一致性)
不要让 LLM 每次都去猜 "GMV" 怎么算。
*   **配置文件**: `metrics.yaml`
    ```yaml
    metrics:
      - name: gmv
        description: "Gross Merchandise Value"
        sql_expression: "sum(order_amount) - sum(refund_amount)"
        dependency_tables: ["orders", "refunds"]
      - name: active_users
        sql_expression: "count(distinct user_id)"
    ```
*   **Compiler 升级**: 当 DSL 出现 `{"metric": "gmv"}` 时，Compiler 自动展开为相应的 SQL Expression。

### 2.2 自动 Join 推断 (Join Graph)
不要让 LLM 处理多表关联，它很容易搞错 `LEFT JOIN` 和 `INNER JOIN`。
*   **图谱构建**: 在元数据层定义表之间的关系 (Foreign Keys)。
*   **路径查找**: Compiler 使用 `NetworkX` 或类似算法，自动寻找从 `Fact Table` 到 `Dimension Table` 的最短 Join 路径。
*   **LLM 减负**: LLM 只需要说 "我要看 User 的 Region 和 Orders 的 GMV"，Compiler 自动补全 `User JOIN Orders ON User.id = Orders.user_id`。

---

## 阶段三：治理与安全 (Week 9-12)

**目标**：解决 "安全" 与 "可观测" 问题。

### 3.1 细粒度权限控制 (Row/Column Security)
*   **Policy Engine**: 在 Compiler 层注入安全策略。
*   **列级**: 用户 A 不能访问 `salary` 字段 -> 如果 DSL 包含该字段，Compiler 直接抛出 `PermissionDenied`。
*   **行级**: 用户 B 只能看 `region='CN'` 的数据 -> Compiler 自动在生成的 SQL `WHERE` 子句中强制追加 `AND region = 'CN'`。

### 3.2 血缘与审计 (Lineage & Audit)
*   **结构化日志**: 记录每一次查询的 `(User, NL_Query, DSL, Generated_SQL)`。
*   **血缘提取**: 解析 DSL 树，自动生成字段级依赖关系：`Dashboard A 用到了 Metric B，Metric B 依赖 Table C 的 Column D`。
*   **影响面分析**: 当 Table C 变更时，立刻通知所有受影响的 Dashboard 用户。

---

## 阶段四：高级增强 (Long Term)

### 4.1 语义纠错 (Self-Correction Loop)
*   当 Compiler 报错（如 "字段不存在"、"聚合也不合法"）时，将错误信息结构化返回给 LLM。
*   LLM 根据错误信息修正 DSL，重新提交。

### 4.2 性能优化 (Caching & Materialization)
*   因为 DSL 是结构化的，更容易计算 Hash Key。
*   Compiler 识别高频 DSL 模式，自动向 DB 建议创建物化视图或索引。

---

## 总结：实施路径建议

1.  **从一张宽表开始**: 先不要做复杂的 Join 推断，在单张宽表上验证 NL -> DSL -> SQL 的流程。
2.  **固定 10 个核心指标**: 不要试图覆盖所有业务，先搞定 CEO 最关心的 10 个指标。
3.  **灰度上线**: 让内部分析师先使用 DSL 模式（作为 Copilot），即 "你说话，我生成 DSL 给你看，你确认后再跑 SQL"。
