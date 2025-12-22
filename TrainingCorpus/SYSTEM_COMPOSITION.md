# 系统组成分析文档

**数据库**: ps_byz
**验证状态**: Verified via DBHub
**生成时间**: 2025-12-20

---

## 概述
本文档基于**问题驱动探索**方法生成，记录了从用户业务问题出发，推理数据需求，验证数据库结构的完整过程。严格遵循 v06 协议的"先查后写"和"验证通过才交付"原则。

---

## 阶段 0: 问题驱动的领域发现

### 0.1 业务问题集分析
从 `plan/GUIDING_QUESTIONS_PASSENGER.md` 提取的10个业务问题：

**客运计划类**
1. 今天广州白云站有多少趟车？高铁和普速分别有多少？
2. 我想知道 G101 次列车的编组情况，有多少节车厢？
3. 最近一周有哪些车次是停运的？停运原因是什么？

**旅客信息设备类**
4. 车站里那些显示列车信息的大屏幕，总共有多少块？都分布在哪些区域？
5. 有没有设备是坏的或者离线的？怎么能看到设备的健康状态？
6. 候车大厅的显示屏和站台上的显示屏是同一个系统管的吗？

**运营状态类**
7. 现在有列车晚点吗？晚点最久的是哪趟车？
8. 一趟列车从"计划"到"发车"要经过哪些步骤？我能看到当前进度吗？

**统计分析类**
9. 广州白云站日均发送多少趟车？峰值是在什么时间段？
10. 我们的车站数据覆盖了哪些路局？广州局管辖的车站有多少个？

### 0.2 数据需求推理结果
**推理假设** → **实际验证结果**

| 问题类别 | 关键业务名词 | 推理假设的实体 | 实际发现的表 | 匹配度 |
|---------|-------------|---------------|------------|--------|
| 客运计划 | 车站、车次、日期、列车类型 | 车站表、车次计划表、列车类型分类表 | `b_station_dictionary`<br>`pa_busi_plan`<br>`online_detail` | ✅ 高度匹配 |
| 列车编组 | 车次、编组、车厢 | 车次表、编组表、车厢表 | `kyz_dcegettrainsetcarinfo`<br>`kyz_dcegettrainsetequipinfo`<br>`kyz_dcgettrainsetruninfo` | ✅ 精确匹配 |
| 停运状态 | 车次、停运状态、原因 | 运营状态表、原因码表 | `online_detail` (通过`TIME_FLAG`判断)<br>`pa_busi_plan` (通过`pa_plan_state`判断) | ⚠️ 部分匹配 |
| 设备信息 | 车站、显示屏、设备、区域 | 设备表、设备类型表、区域表 | `afc_gate_equipment`<br>`pa_bas_area`<br>`pa_bas_sig_src` | ✅ 高度匹配 |
| 设备状态 | 设备、健康状态、离线状态 | 设备状态表、健康监控表 | `online_detail` (通过`READ_STATE`判断) | ⚠️ 间接匹配 |
| 运营状态 | 列车、晚点状态、延迟时间 | 列车实时状态表、晚点记录表 | `online_detail` (包含`ARR_DELAY`、`DPT_DELAY`) | ✅ 精确匹配 |
| 工作流程 | 列车、计划、发车、步骤、进度 | 列车生命周期表、进度跟踪表 | `pa_busi_plan` (多个状态字段)<br>`kyz_train_work_step_status` | ✅ 高度匹配 |
| 统计分析 | 车站、日均发送量、时间段、峰值 | 车站统计表、时间分布表 | `online_statis`<br>`online_detail` | ✅ 精确匹配 |
| 路局管辖 | 车站、铁路局、管辖范围 | 车站表、铁路局表、管辖关系表 | `b_station_dictionary` (包含`bureau_code`)<br>`a_jcdept_bureau` | ✅ 精确匹配 |

### 0.3 核心实体清单及判定理由

#### 1. 静态配置表 (变化少，基础数据)
| 表名 | 记录数 | 判定理由 | 支持的业务问题 |
|------|--------|----------|----------------|
| `b_station_dictionary` | 4,774 | 存储车站基础信息，包含路局代码、启用停用日期等 | Q1, Q10 |
| `afc_gate_equipment` | 172 | 存储AFC门禁设备基本信息 | Q4, Q5 |
| `pa_bas_area` | 56 | 存储基础区域配置信息 | Q4, Q6 |
| `pa_bas_sig_src` | 17 | 存储信号源配置信息 | Q6 |
| `a_jcdept_bureau` | 347 | 存储路局部门信息 | Q10 |

#### 2. 业务单据表 (频繁操作，有时效性)
| 表名 | 记录数 | 判定理由 | 支持的业务问题 |
|------|--------|----------|----------------|
| `pa_busi_plan` | 65,765 | 客运业务计划，包含时间、状态、关联ID | Q1, Q3, Q8 |
| `pa_busi_plan_area` | 719,249 | 业务计划区域关联，高频更新 | Q4, Q6 |
| `kyz_dcegettrainsetcarinfo` | 133,268 | 列车编组车厢信息，包含创建时间 | Q2 |
| `kyz_dcegettrainsetequipinfo` | 17,819 | 列车编组设备信息 | Q2 |
| `kyz_dcgettrainsetruninfo` | 10,007 | 列车编组运行信息 | Q2 |
| `online_detail` | 185,421 | 列车实时状态，包含晚点信息，频繁更新 | Q1, Q3, Q7, Q9 |
| `online_statis` | 5,779 | 在线统计信息，支持分析查询 | Q9 |
| `kyz_kyglsumpeople_detail` | 1,312 | 客运汇总详情，支持统计分析 | Q9 |

### 0.4 关键发现与验证结论

#### 验证成功的推理假设
1. **车站与路局关系**: `b_station_dictionary.bureau_code` 字段验证了车站与路局的归属关系
2. **列车编组信息**: `kyz_dcegettrainsetcarinfo` 表包含 `S_TRAINSETID` 和 `I_CARSEQUENCE`，可回答车厢数量问题
3. **晚点状态**: `online_detail` 表包含 `ARR_DELAY` 和 `DPT_DELAY` 字段，直接记录晚点分钟数
4. **设备分布**: `afc_gate_equipment` 与 `pa_bas_area` 通过 `rela_tree_id` 关联，可回答设备分布问题

#### 需要进一步验证的假设
1. **停运原因**: 尚未发现明确的"停运原因码表"，可能通过状态组合或外部系统判断
2. **设备健康状态**: 设备状态可能通过 `online_detail.READ_STATE` 或 `pa_busi_plan.run_state` 间接判断
3. **系统管理关系**: 候车大厅与站台显示屏是否同一系统，需要验证设备与区域、系统的关联关系

#### 数据量级评估
- **小规模静态数据**: 车站字典(4.7K)、设备表(172)、区域表(56)等
- **中等规模业务数据**: 客运计划(65K)、编组信息(133K)、客运统计(1.3K)等
- **大规模实时数据**: 在线详情(185K)、计划区域关联(719K)等

---

## 问题→数据实体映射总结

### 可直接回答的问题
1. **今天广州白云站有多少趟车？** → `online_detail` + `b_station_dictionary`
2. **G101次列车的编组情况？** → `kyz_dcegettrainsetcarinfo` + `kyz_dcegettrainsetequipinfo`
3. **现在有列车晚点吗？** → `online_detail` (ARR_DELAY/DPT_DELAY)
4. **车站数据覆盖哪些路局？** → `b_station_dictionary` + `a_jcdept_bureau`
5. **设备分布情况？** → `afc_gate_equipment` + `pa_bas_area`

### 需要组合查询的问题
6. **高铁和普速分别有多少？** → `online_detail` + 列车类型判断逻辑
7. **停运的车次及原因？** → `online_detail` + `pa_busi_plan` + 状态码翻译
8. **设备健康状态？** → `afc_gate_equipment` + `online_detail` 状态关联
9. **日均发送车次及峰值？** → `online_detail` + `online_statis` 时间聚合

### 需要深入探索的问题
10. **计划到发车的步骤进度？** → `pa_busi_plan` + `kyz_train_work_step_status` 工作流分析

---

**文档验证状态**: ✅ 所有数据表名和字段名已通过 `mcp_dbhub_search_objects` 和 `mcp_dbhub_execute_sql` 验证
**下次更新时间**: 阶段1完成后更新业务流程与数据流向分析