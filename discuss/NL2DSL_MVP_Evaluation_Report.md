# NL2DSL MVP 有效性评估报告

**版本**: 1.0  
**日期**: 2025-12-15  
**作者**: Vanna NL2DSL Team

---

## 1. 执行摘要

本报告评估了 NL2DSL MVP（最小可行产品）相对于 Vanna 标准 SQL 生成方法的有效性。

### 核心结论

> **在分析查询场景下，NL2DSL 方法（95%）比 Vanna 标准 SQL 生成（~79%）高出约 16 个百分点。DSL 的结构化输出和编译器机制提供了更高的准确性和稳定性。**

| 指标 | NL2DSL | Vanna SQL |
| :--- | :--- | :--- |
| 准确率（语义等价） | **95%** | **79%** |
| 执行错误重试 | 0 次 | 2 次 |
| 语法错误 | 0 | 0 |

---

## 2. 评估方法

### 2.1 测试数据

- **Golden Set**: `tests/data/golden_ticket_20.jsonl`
- **数据量**: 20 条自然语言问题
- **数据库**: SQLite (`TicketDB/ticket.db`)
- **目标表**: `sale_record0523`（火车票销售数据）

### 2.2 测试场景覆盖

| 场景类型 | 数量 | 示例 |
| :--- | :--- | :--- |
| 简单聚合 | 5 | "What is the total ticket price?" |
| 过滤条件 | 4 | "Total sales for 'Beijing' departure station" |
| 分组聚合 | 5 | "Total sales by sale mode" |
| 排序 + 限制 | 2 | "Top 5 departure stations by sales" |
| 时间粒度 | 2 | "Total sales by year" |
| 复合条件 | 2 | "Sales for 'Shanghai' or 'Guangzhou'" |

### 2.3 评估脚本

| 脚本 | 用途 |
| :--- | :--- |
| `evaluate_fair_comparison.py` | 公平比较（语义等价） |
| `evaluate_agent_comparison.py` | Agent 启用比较（含修正循环） |

### 2.4 LLM 配置

- **模型**: Qwen3-Coder-30B
- **端点**: 本地 LM Studio (`http://127.0.0.1:1234/v1`)
- **温度**: 0.0（确定性输出）

---

## 3. 评估结果

### 3.1 多轮评估对比

| 轮次 | 比较方式 | NL2DSL | Vanna SQL | 差距 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 格式敏感 | 95% | 52.63% | 42.37% |
| 2 | 语义等价 | 95% | 80% | 15% |
| 3 | Agent 启用 | 95% | 78.95% | 16.05% |

> **注**: 格式敏感比较因列顺序、别名差异导致虚高差距。语义等价比较更能反映真实能力差距。

### 3.2 失败分析

#### NL2DSL 失败案例（1/20）
| 问题 | 失败原因 |
| :--- | :--- |
| Q8: "Top 5 departure stations" | LLM 生成 `asc` 而非 `desc` |

#### Vanna SQL 失败案例（4/20）
| 问题 | 失败原因 |
| :--- | :--- |
| Q4, Q7, Q10, Q19 | 列顺序/排序方向/额外 ORDER BY |

### 3.3 Agent 修正效果

| 方法 | 修正前 | 修正后 | 重试次数 |
| :--- | :--- | :--- | :--- |
| NL2DSL | 95% | 95% | 0 |
| Vanna SQL | ~78% | 78.95% | 2 |

**结论**: Agent 修正机制对逻辑错误（如排序方向）效果有限，主要对语法错误有效。

---

## 4. 技术优势分析

### 4.1 NL2DSL 架构优势

```
问题 → LLM → JSON DSL → Pydantic 验证 → SQL 编译器 → SQL
         ↑                    ↓
      重试（如验证失败）    语法保证
```

| 优势 | 描述 |
| :--- | :--- |
| **结构化输出** | JSON 格式便于验证和调试 |
| **模式验证** | Pydantic 确保 DSL 结构正确 |
| **编译器保证** | SQL 语法由编译器生成，不依赖 LLM |
| **可重试性** | 验证失败可自动重试，成本低 |

### 4.2 直接 SQL 生成的劣势

| 劣势 | 描述 |
| :--- | :--- |
| 格式多样性 | LLM 可能生成多种等价但格式不同的 SQL |
| 验证困难 | 难以在执行前验证 SQL 正确性 |
| 修正成本 | 执行失败后修正需要完整重新生成 |

---

## 5. 局限性与威胁效度

### 5.1 内部效度威胁

| 威胁 | 缓解措施 |
| :--- | :--- |
| Ground Truth 偏向 DSL | 使用语义等价比较 |
| 评估脚本 bug | 多轮评估交叉验证 |

### 5.2 外部效度威胁

| 威胁 | 当前状态 | 建议 |
| :--- | :--- | :--- |
| 样本量小（20条） | ⚠️ 未缓解 | 扩展到 50+ 条 |
| 单一表结构 | ⚠️ 未缓解 | 添加多表测试 |
| 单一数据库 | ⚠️ 未缓解 | PostgreSQL 验证 |
| 单一 LLM | ⚠️ 未缓解 | GPT-4/Llama 验证 |

---

## 6. 结论与建议

### 6.1 结论

基于本次评估，**初步证明 NL2DSL MVP 的有效性**：

1. **准确性提升**: 相比 Vanna SQL，DSL 方法提升约 16%
2. **稳定性更高**: DSL 无需执行错误重试
3. **可维护性更强**: 结构化输出便于调试和扩展

### 6.2 建议

#### 短期（P0）
- [ ] 修复 Q8 排序方向问题（优化 Prompt）
- [ ] 扩展 Golden Set 到 50 条

#### 中期（P1）
- [ ] 添加多表（JOIN）支持和测试
- [ ] PostgreSQL 方言验证
- [ ] 添加 HAVING 子句支持

#### 长期（P2）
- [ ] 集成 Spider 数据集进行标准化评估
- [ ] 跨 LLM 验证（GPT-4、Claude、Llama）

---

## 7. 附录

### 7.1 评估数据文件

| 文件 | 描述 |
| :--- | :--- |
| `tests/data/golden_ticket_20.jsonl` | Golden Set 数据 |
| `eval_fair_comparison_results.csv` | 语义等价评估结果 |
| `eval_agent_comparison_results.csv` | Agent 启用评估结果 |

### 7.2 评估脚本

| 脚本 | 描述 |
| :--- | :--- |
| `tests/evaluation/evaluate_fair_comparison.py` | 公平比较脚本 |
| `tests/evaluation/evaluate_agent_comparison.py` | Agent 启用比较脚本 |
| `tests/evaluation/debug_failures.py` | 失败案例调试脚本 |

### 7.3 相关技术文档

- [NL2DSL 技术设计](../discuss/NL2DSL_MVP_Technical_Design.md)
- [DSL Schema 定义](../src/vanna/dsl/schema.py)
- [DSL 编译器实现](../src/vanna/dsl/compiler.py)

---

*报告结束*
