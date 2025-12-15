# ErrorRecoveryStrategy 详细解读与重试机制配置指南

> 讨论生成时间：2025-12-12
>
> 基于 Vanna 2.0 源代码深入分析

## 目录

1. [架构分析](#架构分析)
2. [核心组件](#核心组件)
3. [重要发现](#重要发现)
4. [可用的重试机制配置](#可用的重试机制配置)
5. [配置建议和最佳实践](#配置建议和最佳实践)
6. [常见问题和解决方案](#常见问题和解决方案)
7. [总结](#总结)

---

## 架构分析

### 1. 核心架构

ErrorRecoveryStrategy 是 Vanna 2.0 中用于**错误处理和重试机制**的可插拔策略接口。它提供了灵活的扩展点，允许开发者自定义错误处理行为。

**类层次结构：**

```
ErrorRecoveryStrategy (抽象基类)
    ├── handle_tool_error()         # 处理工具执行错误
    └── handle_llm_error()          # 处理 LLM 通信错误

RecoveryAction (数据模型)
    ├── action: RecoveryActionType
    ├── retry_delay_ms: Optional[int]
    ├── fallback_value: Optional[Any]
    └── message: Optional[str]

RecoveryActionType (枚举)
    ├── RETRY      # 重试操作
    ├── FAIL       # 失败并返回错误
    ├── FALLBACK   # 使用备选方案
    └── SKIP       # 跳过操作继续执行
```

**源码位置：**
- `src/vanna/core/recovery/base.py`: 策略接口定义
- `src/vanna/core/recovery/models.py`: 数据模型
- `src/vanna/core/agent/agent.py`: Agent 集成点（第 123 行）
- `src/vanna/core/registry.py`: 工具执行（第 144-279 行）

### 2. 工作流程

```
工具执行失败
   ↓
ErrorRecoveryStrategy.handle_tool_error()
   ↓
返回 RecoveryAction
   ↓
├─ RETRY → 延迟后重试
├─ FAIL → 返回错误结果
├─ FALLBACK → 使用备选值
└─ SKIP → 跳过操作
```

---

## 核心组件

### 1. RecoveryActionType

**定义**（`src/vanna/core/recovery/models.py:11-18`）：

```python
class RecoveryActionType(str, Enum):
    RETRY = "retry"      # 重试操作
    FAIL = "fail"        # 失败并返回错误
    FALLBACK = "fallback" # 使用备选方案
    SKIP = "skip"        # 跳过操作继续执行
```

**使用场景：**

| 类型 | 适用场景 | 返回值 |
|------|---------|--------|
| `RETRY` | 临时性错误（网络超时、连接断开） | `retry_delay_ms` 指定延迟 |
| `FAIL` | 永久错误（语法错误、权限不足） | 错误消息 |
| `FALLBACK` | 可降级操作（可视化失败返回表格） | `fallback_value` 作为备选结果 |
| `SKIP` | 非关键操作（计算器失败不影响主流程） | 跳过说明 |

### 2. RecoveryAction

**定义**（`src/vanna/core/recovery/models.py:20-33`）：

```python
class RecoveryAction(BaseModel):
    action: RecoveryActionType              # 动作类型
    retry_delay_ms: Optional[int] = None    # 重试延迟（毫秒）
    fallback_value: Optional[Any] = None    # 备选值（用于 FALLBACK）
    message: Optional[str] = None           # 消息/原因
```

**字段说明：**

- `action`: 必选字段，指定要采取的动作
- `retry_delay_ms`: RETRY 动作时必选，指定延迟时间（毫秒）
- `fallback_value`: FALLBACK 动作时必选，提供备选结果
- `message`: 可选，用于日志和调试

### 3. ErrorRecoveryStrategy 接口

**定义**（`src/vanna/core/recovery/base.py:18-85`）：

```python
class ErrorRecoveryStrategy(ABC):
    """策略接口"""

    async def handle_tool_error(
        self, error: Exception, context: ToolContext, attempt: int = 1
    ) -> RecoveryAction:
        """处理工具执行错误（默认：立即失败）"""
        return RecoveryAction(
            action=RecoveryActionType.FAIL,
            message=f"Tool error: {str(error)}"
        )

    async def handle_llm_error(
        self, error: Exception, request: LlmRequest, attempt: int = 1
    ) -> RecoveryAction:
        """处理 LLM 通信错误（默认：立即失败）"""
        return RecoveryAction(
            action=RecoveryActionType.FAIL,
            message=f"LLM error: {str(error)}"
        )
```

**参数说明：**

- `error`: 捕获的异常对象
- `context`: 工具执行上下文（包含用户信息、请求ID等）
- `attempt`: 当前重试次数（从 1 开始）

---

## 重要发现

### ⚠️ 关键问题：尚未完全集成

经过深入分析，发现一个重要事实：**ErrorRecoveryStrategy 尚未完全集成到 Agent 执行流程中！**

#### 证据分析

**1. Agent 存储策略位置**（`src/vanna/core/agent/agent.py:123`）：

```python
self.error_recovery_strategy = error_recovery_strategy  # 仅存储，未调用
```

**2. ToolRegistry.execute() 实现**（`src/vanna/core/registry.py:271-278`）：

```python
try:
    start_time = time.perf_counter()
    result = await tool.execute(context, final_args)  # 直接执行
    execution_time_ms = (time.perf_counter() - start_time) * 1000
    result.metadata["execution_time_ms"] = execution_time_ms
    return result
except Exception as e:
    msg = f"Execution failed: {str(e)}"
    return ToolResult(           # ❌ 直接返回错误，没有触发重试
        success=False,
        result_for_llm=msg,
        ui_component=None,
        error=msg,
    )
```

**3. 全局代码搜索**：

```bash
$ grep -r "handle_tool_error" src/vanna
src/vanna/examples/extensibility_example.py  # 仅示例14
src/vanna/core/recovery/base.py               # 接口定义

$ grep -r "error_recovery_strategy" src/vanna
src/vanna/core/agent/agent.py                 # 仅存储
src/vanna/examples/extensibility_example.py   # 仅示例
```

#### 结论

**ErrorRecoveryStrategy 是一个设计良好的扩展点，但尚未实现完整的集成。** 它是一个**前瞻性设计**，为未来版本预留的扩展能力。

#### 影响

目前无法直接在 Agent 中使用 ErrorRecoveryStrategy，需要我们**自行实现重试逻辑**。

---

## 可用的重试机制配置

### 方案 1：自定义 RetryableToolRegistry（推荐）

创建一个支持错误重试的工具注册表，这是最灵活和可用的方案。

#### 实现代码

```python
from vanna.core.registry import ToolRegistry
from vanna.core.recovery import ErrorRecoveryStrategy, RecoveryActionType
from vanna.core.tool import ToolCall, ToolContext, ToolResult
import asyncio
import time

class RetryableToolRegistry(ToolRegistry):
    """支持错误重试的工具注册表"""

    def __init__(
        self,
        error_recovery_strategy: ErrorRecoveryStrategy = None,
        audit_logger=None,
        audit_config=None,
    ):
        super().__init__(audit_logger, audit_config)
        self.error_recovery_strategy = error_recovery_strategy

    async def execute(
        self,
        tool_call: ToolCall,
        context: ToolContext,
    ) -> ToolResult:
        """执行工具调用，支持错误重试"""

        # 获取工具
        tool = await self.get_tool(tool_call.name)
        if not tool:
            msg = f"Tool '{tool_call.name}' not found"
            return ToolResult(
                success=False, result_for_llm=msg, ui_component=None, error=msg
            )

        # 验证权限
        if not await self._validate_tool_permissions(tool, context.user):
            msg = f"Insufficient group access for tool '{tool_call.name}'"
            return ToolResult(
                success=False, result_for_llm=msg, ui_component=None, error=msg
            )

        # 验证参数
        try:
            args_model = tool.get_args_schema()
            validated_args = args_model.model_validate(tool_call.arguments)
        except Exception as e:
            msg = f"Invalid arguments: {str(e)}"
            return ToolResult(
                success=False, result_for_llm=msg, ui_component=None, error=msg
            )

        # 转换参数
        transform_result = await self.transform_args(
            tool=tool,
            args=validated_args,
            user=context.user,
            context=context,
        )

        if isinstance(transform_result, ToolRejection):
            return ToolResult(
                success=False,
                result_for_llm=transform_result.reason,
                ui_component=None,
                error=transform_result.reason,
            )

        final_args = transform_result

        # 执行工具（带重试逻辑）
        if self.error_recovery_strategy:
            return await self._execute_with_retry(
                tool, context, final_args, tool_call
            )
        else:
            return await self._execute_once(tool, context, final_args, tool_call)

    async def _execute_with_retry(
        self,
        tool,
        context: ToolContext,
        final_args,
        tool_call: ToolCall,
        max_attempts: int = 3,
    ) -> ToolResult:
        """带重试逻辑的工具执行"""

        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                # 执行工具
                start_time = time.perf_counter()
                result = await tool.execute(context, final_args)
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                result.metadata["execution_time_ms"] = execution_time_ms

                # 审计成功执行
                await self._audit_execution(tool_call, context, result, attempt)

                # 如果之前有失败，记录最终成功
                if attempt > 1:
                    print(f"✅ Success on attempt {attempt}")

                return result

            except Exception as e:
                last_error = e

                # 调用错误恢复策略
                recovery_action = await self.error_recovery_strategy.handle_tool_error(
                    error=e, context=context, attempt=attempt
                )

                print(
                    f"❌ Attempt {attempt}/{max_attempts} failed: {str(e)}\n"
                    f"   Action: {recovery_action.action}\n"
                    f"   Message: {recovery_action.message}"
                )

                # 根据恢复动作类型处理
                if recovery_action.action == RecoveryActionType.RETRY:
                    # 延迟后重试
                    delay_ms = recovery_action.retry_delay_ms or 0
                    if delay_ms > 0:
                        print(f"   Waiting {delay_ms}ms before retry...")
                        await asyncio.sleep(delay_ms / 1000.0)
                    continue  # 继续下一次尝试

                elif recovery_action.action == RecoveryActionType.FAIL:
                    # 立即失败
                    break

                elif recovery_action.action == RecoveryActionType.FALLBACK:
                    # 返回默认值
                    return ToolResult(
                        success=True,
                        result_for_llm=str(recovery_action.fallback_value),
                        ui_component=None,
                        metadata={"fallback_used": True, "attempt": attempt},
                    )

                elif recovery_action.action == RecoveryActionType.SKIP:
                    # 跳过操作
                    return ToolResult(
                        success=True,
                        result_for_llm="Operation skipped",
                        ui_component=None,
                        metadata={"skipped": True, "attempt": attempt},
                    )

        # 所有重试都失败
        error_msg = (
            f"Execution failed after {max_attempts} attempts: {str(last_error)}"
        )
        return ToolResult(
            success=False,
            result_for_llm=error_msg,
            ui_component=None,
            error=error_msg,
        )

    async def _execute_once(self, tool, context, final_args, tool_call):
        """单次执行，不尝试重试"""
        try:
            start_time = time.perf_counter()
            result = await tool.execute(context, final_args)
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            result.metadata["execution_time_ms"] = execution_time_ms

            await self._audit_execution(tool_call, context, result, 1)
            return result
        except Exception as e:
            msg = f"Execution failed: {str(e)}"
            return ToolResult(
                success=False, result_for_llm=msg, ui_component=None, error=msg
            )

    async def _audit_execution(self, tool_call, context, result, attempt):
        """审计工具执行情况"""
        if not self.audit_logger or not self.audit_config:
            return

        # 添加重试信息到元数据
        if attempt > 1:
            result.metadata["retry_attempt"] = attempt

        if self.audit_config.log_tool_invocations:
            ui_features = context.metadata.get("ui_features_available", [])
            await self.audit_logger.log_tool_invocation(
                user=context.user,
                tool_call=tool_call,
                ui_features=ui_features,
                context=context,
                sanitize_parameters=self.audit_config.sanitize_tool_parameters,
            )

        if self.audit_config.log_tool_results:
            await self.audit_logger.log_tool_result(
                user=context.user,
                tool_call=tool_call,
                result=result,
                context=context,
            )
```

#### 优点

- ✅ **无需修改 Vanna 核心代码**
- ✅ **完全兼容现有接口**
- ✅ **可灵活配置重试策略**
- ✅ **支持审计和监控**
- ✅ **保留原始 ToolRegistry 的所有功能**

#### 使用示例

```python
from vanna.core.registry import ToolRegistry
from vanna.tools import RunSqlTool
from vanna.integrations.sqlite import SqliteRunner

# 1. 创建重试策略
recovery_strategy = ExponentialBackoffStrategy(max_retries=3)

# 2. 创建支持重试的工具注册表
tool_registry = RetryableToolRegistry(error_recovery_strategy=recovery_strategy)

# 3. 注册工具（与正常使用完全相同）
sql_runner = SqliteRunner("./data.db")
tool_registry.register(RunSqlTool(sql_runner))

# 4. 传递给 Agent
agent = Agent(
    llm_service=llm_service,
    tool_registry=tool_registry,  # 使用重试注册表
    user_resolver=user_resolver,
    agent_memory=agent_memory,
)
```

---

### 方案 2：自定义错误恢复策略

提供多种预构建的错误恢复策略，适用于不同场景。

#### 策略 1：指数退避重试（ExponentialBackoffStrategy）

适用于临时性网络故障、数据库连接问题等。

```python
from vanna.core.recovery import ErrorRecoveryStrategy, RecoveryAction, RecoveryActionType
from vanna.core.tool import ToolContext
from vanna.core.llm import LlmRequest
import logging
import random

logger = logging.getLogger(__name__)

class ExponentialBackoffStrategy(ErrorRecoveryStrategy):
    """指数退避重试策略

    适用于：
    - 网络超时
    - 连接错误
    - 临时性数据库不可用
    - API 限流

    参数：
    - max_retries: 最大重试次数（默认 3）
    - initial_delay_ms: 初始延迟（默认 1000ms）
    - max_delay_ms: 最大延迟（默认 10000ms）
    - retryable_errors: 可重试的异常类型
    - non_retryable_errors: 不可重试的异常类型
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay_ms: int = 1000,
        max_delay_ms: int = 10000,
        retryable_errors: tuple = (
            TimeoutError, ConnectionError, OSError
        ),
        non_retryable_errors: tuple = (ValueError, TypeError, AttributeError),
    ):
        self.max_retries = max_retries
        self.initial_delay_ms = initial_delay_ms
        self.max_delay_ms = max_delay_ms
        self.retryable_errors = retryable_errors
        self.non_retryable_errors = non_retryable_errors

    def _should_retry(self, error: Exception) -> bool:
        """判断错误是否应该重试"""

        # 1. 非重试错误（立即失败）
        if isinstance(error, self.non_retryable_errors):
            return False

        # 2. 可重试错误
        if isinstance(error, self.retryable_errors):
            return True

        # 3. 根据错误消息判断
        error_msg = str(error).lower()

        # 数据库连接错误
        if any(
            keyword in error_msg
            for keyword in [
                "connection",
                "timeout",
                "network",
                "unreachable",
                "refused",
                "reset",
                "broken pipe",
                "ssl",
            ]
        ):
            return True

        # SQL 语法错误（不重试）
        if any(
            keyword in error_msg
            for keyword in ["syntax error", "syntax_error", "invalid sql", "sql syntax"]
        ):
            return False

        # 权限错误（不重试）
        if any(
            keyword in error_msg
            for keyword in ["permission denied", "access denied", "unauthorized", "forbidden"]
        ):
            return False

        # 默认：不重试（安全优先）
        return False

    def _calculate_delay(self, attempt: int) -> int:
        """计算重试延迟（指数退避 + 抖动）"""

        # 指数退避：delay = initial * 2^(attempt-1)
        delay_ms = self.initial_delay_ms * (2 ** (attempt - 1))

        # 上限保护
        delay_ms = min(delay_ms, self.max_delay_ms)

        # 添加随机抖动（±25%）避免惊群效应
        jitter = random.uniform(0.75, 1.25)
        delay_ms = int(delay_ms * jitter)

        return delay_ms

    async def handle_tool_error(
        self, error: Exception, context: ToolContext, attempt: int = 1
    ) -> RecoveryAction:
        """处理工具执行错误"""

        # 超过最大重试次数
        if attempt >= self.max_retries:
            logger.error(
                f"[FAIL] Max retries exceeded ({self.max_retries}) for tool error: {error}"
            )
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"Tool failed after {self.max_retries} attempts: {str(error)}",
            )

        # 判断是否应该重试
        if not self._should_retry(error):
            logger.warning(
                f"[FAIL] Non-retryable error encountered: {type(error).__name__}: {error}"
            )
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"Non-retryable error: {str(error)}",
            )

        # 计算延迟
        delay_ms = self._calculate_delay(attempt)

        logger.info(
            f"[RETRY] Tool failed (attempt {attempt}/{self.max_retries}): {error}\n"
            f"        Retrying after {delay_ms}ms"
        )

        return RecoveryAction(
            action=RecoveryActionType.RETRY,
            retry_delay_ms=delay_ms,
            message=f"Retrying after {delay_ms}ms (attempt {attempt}/{self.max_retries})",
        )

    async def handle_llm_error(
        self, error: Exception, request: LlmRequest, attempt: int = 1
    ) -> RecoveryAction:
        """处理 LLM 调用错误"""

        error_msg = str(error).lower()

        # LLM 非重试错误
        if any(
            keyword in error_msg
            for keyword in [
                "invalid",
                "bad request",
                "authentication",
                "unauthorized",
                "quota exceeded",
                "content policy",
                "content filter",
            ]
        ):
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"LLM error (non-retryable): {str(error)}",
            )

        # 超过最大重试次数
        if attempt >= self.max_retries:
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"LLM error after {self.max_retries} attempts: {str(error)}",
            )

        # API 限流、超时、连接错误 → 可重试
        delay_ms = self._calculate_delay(attempt)

        logger.info(
            f"[RETRY] LLM failed (attempt {attempt}/{self.max_retries}): {error}"
        )

        return RecoveryAction(
            action=RecoveryActionType.RETRY,
            retry_delay_ms=delay_ms,
            message=f"Retrying LLM after {delay_ms}ms",
        )
```

#### 策略 2：智能 SQL 错误处理（SmartSqlErrorStrategy）

专门用于处理 SQL 相关的错误，区分语法错误和连接错误。

```python
class SmartSqlErrorStrategy(ErrorRecoveryStrategy):
    """智能 SQL 错误处理策略

    特点：
    - 连接错误 → 重试
    - 语法错误 → 不重试，让 LLM 修正
    - 超时 → 建议简化查询
    - 权限错误 → 立即失败
    - 表/列不存在 → 让 LLM 修正
    """

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    async def handle_tool_error(
        self, error: Exception, context: ToolContext, attempt: int = 1
    ) -> RecoveryAction:
        """处理 SQL 执行错误"""

        error_msg = str(error).lower()

        # 1. 连接错误（可重试）
        if any(keyword in error_msg for keyword in ["connection", "timeout", "network"]):
            if attempt <= self.max_retries:
                return RecoveryAction(
                    action=RecoveryActionType.RETRY,
                    retry_delay_ms=2000 * attempt,  # 线性退避
                    message=f"Database connection issue, retrying... (attempt {attempt})",
                )

        # 2. 语法错误（不可重试，返回给 LLM 修正）
        if any(keyword in error_msg for keyword in ["syntax", "syntax_error", "invalid sql"]):
            # 不重试，让 LLM 看到错误并修正 SQL
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"SQL syntax error: {str(error)}",
            )

        # 3. 超时错误（可重试，但减少复杂度）
        if "timeout" in error_msg:
            if attempt == 1:
                # 第一次超时，让 LLM 生成更简单的查询
                return RecoveryAction(
                    action=RecoveryActionType.FAIL,
                    message="Query timeout. Suggest simplifying the query or adding LIMIT.",
                )

        # 4. 权限错误（不可重试）
        if "permission" in error_msg or "denied" in error_msg:
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"Permission denied: {str(error)}",
            )

        # 5. 表/列不存在（让 LLM 修正）
        if any(
            keyword in error_msg
            for keyword in ["does not exist", "not found", "invalid table", "invalid column"]
        ):
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"Schema error: {str(error)}",
            )

        # 6. 外键约束错误（数据问题）
        if "foreign key" in error_msg or "constraint" in error_msg:
            return RecoveryAction(
                action=RecoveryActionType.FAIL,
                message=f"Data integrity error: {str(error)}",
            )

        # 默认：不重试
        return RecoveryAction(
            action=RecoveryActionType.FAIL,
            message=f"SQL execution error: {str(error)}",
        )
```

#### 策略 3：优雅降级模式（GracefulDegradationStrategy）

适用于用户体验优先的场景，即使部分功能失败也要提供可用结果。

```python
class GracefulDegradationStrategy(ErrorRecoveryStrategy):
    """优雅降级策略

    处理方案：
    - 可视化失败 → 返回表格数据
    - 复杂查询失败 → 建议简化查询
    - 外部 API 失败 → 使用缓存或返回可用数据
    - 非关键操作失败 → 跳过继续执行
    """

    def __init__(self, enable_fallbacks: bool = True):
        self.enable_fallbacks = enable_fallbacks

    async def handle_tool_error(
        self, error: Exception, context: ToolContext, attempt: int = 1
    ) -> RecoveryAction:
        """根据错误类型选择降级方案"""

        error_msg = str(error).lower()
        tool_name = context.metadata.get("tool_name", "")

        # 1. 可视化失败 → 返回表格数据
        if "visualize" in tool_name or "chart" in tool_name:
            return RecoveryAction(
                action=RecoveryActionType.FALLBACK,
                fallback_value={
                    "message": "Chart creation failed, but data is available in table format.",
                    "suggestion": "Use the table data or try a different chart type.",
                    "fallback_type": "visualization",
                },
                message="Falling back to table data due to visualization error",
            )

        # 2. 复杂查询失败 → 建议简化查询
        if "timeout" in error_msg or "memory" in error_msg:
            return RecoveryAction(
                action=RecoveryActionType.FALLBACK,
                fallback_value={
                    "message": "Complex query failed. Try querying a smaller date range or fewer columns.",
                    "suggestion": "Add LIMIT 1000 or filter by specific date range.",
                    "fallback_type": "query_simplification",
                },
                message="Query too complex, suggesting simplification",
            )

        # 3. 外部 API 失败 → 返回友好提示
        if "api" in error_msg or "connection" in error_msg:
            return RecoveryAction(
                action=RecoveryActionType.FALLBACK,
                fallback_value={
                    "message": "External service temporarily unavailable.",
                    "suggestion": "Try again in a few minutes or use local data sources.",
                    "fallback_type": "external_api",
                },
                message="External dependency unavailable, using fallback",
            )

        # 4. 计算器/辅助工具失败 → 跳过继续执行
        if any(
            keyword in tool_name
            for keyword in ["calculator", "calc", "helper", "utility"]
        ):
            return RecoveryAction(
                action=RecoveryActionType.SKIP,
                message="Non-critical tool failed, continuing with main analysis.",
            )

        # 5. 数据采集失败 → 返回缓存数据
        if "fetch" in tool_name or "retrieve" in tool_name:
            return RecoveryAction(
                action=RecoveryActionType.FALLBACK,
                fallback_value={
                    "message": "Failed to fetch fresh data.",
                    "suggestion": "Showing cached data from previous queries.",
                    "fallback_type": "cached_data",
                    "stale": True,
                },
                message="Using cached data due to fetch failure",
            )

        # 默认：失败
        return RecoveryAction(action=RecoveryActionType.FAIL, message=f"Tool error: {str(error)}")
```

#### 策略 4：组合策略（CompositeErrorStrategy）

按优先级组合多个策略。

```python
from typing import List

class CompositeErrorStrategy(ErrorRecoveryStrategy):
    """组合多个策略，按优先级执行

    执行流程：
    1. 按顺序调用各个策略
    2. 如果策略决定 RETRY，立即采用
    3. 如果策略提供降级方案（FALLBACK/SKIP），采用第一个
    4. 所有策略都建议 FAIL，则最终失败
    """

    def __init__(self, strategies: List[ErrorRecoveryStrategy]):
        if not strategies:
            raise ValueError("At least one strategy is required")
        self.strategies = strategies

    async def handle_tool_error(
        self, error: Exception, context: ToolContext, attempt: int = 1
    ) -> RecoveryAction:
        """按顺序尝试各个策略"""

        for i, strategy in enumerate(self.strategies):
            action = await strategy.handle_tool_error(error, context, attempt)

            # 如果策略决定重试，立即采用
            if action.action == RecoveryActionType.RETRY:
                logger.info(
                    f"Strategy {i+1}/{len(self.strategies)} "
                    f"({strategy.__class__.__name__}) decided to RETRY"
                )
                return action

            # 如果策略提供降级方案，记录但继续（优先采用第一个）
            if action.action in [RecoveryActionType.FALLBACK, RecoveryActionType.SKIP]:
                logger.info(
                    f"Strategy {i+1}/{len(self.strategies)} "
                    f"({strategy.__class__.__name__}) decided to {action.action}"
                )
                # 找到第一个降级方案就返回
                return action

        # 所有策略都建议失败
        return RecoveryAction(
            action=RecoveryActionType.FAIL,
            message=f"All strategies failed to handle: {str(error)}",
        )
```

#### 使用组合策略示例

```python
# 创建多个策略
exponential_backoff = ExponentialBackoffStrategy(
    max_retries=3, initial_delay_ms=1000
)
smart_sql = SmartSqlErrorStrategy(max_retries=2)
graceful_degradation = GracefulDegradationStrategy()

# 组合策略（按优先级）
# 优先级：重试 > 智能 SQL 处理 > 优雅降级
composite_strategy = CompositeErrorStrategy(
    strategies=[exponential_backoff, smart_sql, graceful_degradation]
)

# 使用
registry = RetryableToolRegistry(error_recovery_strategy=composite_strategy)
```

---

### 方案 3：完整的 Agent 配置示例

提供从创建到使用的完整流程。

#### 完整配置代码

```python
import asyncio
from vanna import Agent, ToolRegistry
from vanna.core.agent.config import AgentConfig
from vanna.core.UserResolver import UserResolver
from vanna.core.user import User
from vanna.integrations.anthropic import AnthropicLlmService
from vanna.integrations.sqlite import SqliteRunner, RunSqlTool
from vanna.integrations.local import InMemoryAgentMemory


async def setup_agent_with_retry():
    """配置支持重试的完整 Agent"""

    # 1. 配置 LLM 服务
    llm_service = AnthropicLlmService(
        api_key="your-anthropic-api-key",  # 或使用环境变量
        model="claude-sonnet-4-20250514",
    )

    # 2. 创建错误恢复策略
    recovery_strategy = ExponentialBackoffStrategy(
        max_retries=3,
        initial_delay_ms=1000,
        max_delay_ms=10000,
        retryable_errors=(TimeoutError, ConnectionError, OSError),
    )

    # 3. 创建支持重试的工具注册表
    tool_registry = RetryableToolRegistry(error_recovery_strategy=recovery_strategy)

    # 4. 注册 SQL 工具
    sql_runner = SqliteRunner("./sales_database.db")
    tool_registry.register(RunSqlTool(sql_runner))

    # 5. 创建用户解析器
    class SimpleUserResolver(UserResolver):
        async def resolve_user(self, request_context):
            return User(
                id="user_123",
                name="Alice",
                email="alice@example.com",
                group_memberships=["analyst", "marketing"],
                metadata={"department": "Marketing", "timezone": "UTC"},
            )

    # 6. 配置 Agent 内存
    agent_memory = InMemoryAgentMemory()
    # 或者使用向量数据库：
    # from vanna.integrations.chroma import ChromaVectorStore
    # agent_memory = SimpleVectorAgentMemory(
    #     vector_store=ChromaVectorStore(path="./memory")
    # )

    # 7. 创建并配置 Agent
    agent = Agent(
        llm_service=llm_service,
        tool_registry=tool_registry,
        user_resolver=SimpleUserResolver(),
        agent_memory=agent_memory,
        config=AgentConfig(
            max_tool_iterations=10,  # 最多 10 次工具调用
            auto_save_conversations=True,  # 自动保存对话
            conversation_filters=[],  # 可以添加对话过滤器
            temperature=0.1,  # 较低温度，保证输出稳定性
            max_tokens=4000,  # 最大输出长度
            stream_responses=True,  # 流式响应
        ),
        error_recovery_strategy=recovery_strategy,  # 保留配置
    )

    return agent


# 使用示例
async def main():
    """使用配置了重试机制的 Agent"""

    # 创建 Agent
    agent = await setup_agent_with_retry()

    # 模拟请求上下文
    from vanna.core.user.request_context import RequestContext

    request_context = RequestContext(
        headers={"user-agent": "CLI-Client/1.0"},
        metadata={"source": "cli", "timestamp": "2025-12-12T10:30:00Z"},
    )

    # 示例 1：简单查询（可能因网络抖动而重试）
    print("=" * 80)
    print("Example 1: Simple SQL Query")
    print("=" * 80)

    async for component in agent.send_message(
        request_context=request_context,
        message="Show me sales data for last month",
        conversation_id="demo_001",
    ):
        # 错误会被自动重试
        print(f"Component: {type(component).__name__}")
        if hasattr(component, "rich_component"):
            print(f"Content: {component.rich_component}")

    # 示例 2：复杂查询（可能超时并多次重试）
    print("\n" + "=" * 80)
    print("Example 2: Complex Aggregation Query")
    print("=" * 80)

    async for component in agent.send_message(
        request_context=request_context,
        message=(
            "Calculate total revenue by product category, month, and region, "
            "with comparisons to last year and profit margins"
        ),
        conversation_id="demo_002",
    ):
        print(f"Component: {type(component).__name__}")

    # 示例 3：带可视化的查询
    print("\n" + "=" * 80)
    print("Example 3: Query with Visualization")
    print("=" * 80)

    async for component in agent.send_message(
        request_context=request_context,
        message="Create a bar chart of top 10 products by sales",
        conversation_id="demo_003",
    ):
        print(f"Component: {type(component).__name__}")


# 运行示例
if __name__ == "__main__":
    print("Starting Vanna Agent with Retry Support...")
    asyncio.run(main())
```

#### 生产环境配置示例

```python
import os
from vanna.core.observability import LoggingObservabilityProvider
from vanna.core.lifecycle import AuditLifecycleHook


async def setup_production_agent():
    """生产环境配置"""

    # 1. 配置可观测性
    observability = LoggingObservabilityProvider(
        log_level="INFO",
        enable_metrics=True,
        enable_tracing=True,
    )

    # 2. 组合策略（指数退避 + 智能 SQL + 优雅降级）
    recovery_strategy = CompositeErrorStrategy(
        strategies=[
            ExponentialBackoffStrategy(
                max_retries=3,
                initial_delay_ms=1000,
                max_delay_ms=10000,
            ),
            SmartSqlErrorStrategy(max_retries=2),
            GracefulDegradationStrategy(),
        ]
    )

    # 3. 审计配置
    audit_config = AuditConfig(
        enabled=True,
        log_tool_access_checks=True,
        log_tool_invocations=True,
        log_tool_results=True,
        sanitize_tool_parameters=True,
    )

    # 4. 创建工具注册表
    tool_registry = RetryableToolRegistry(
        error_recovery_strategy=recovery_strategy,
    )

    # 使用环境变量配置数据库连接
    db_path = os.getenv("DATABASE_PATH", "./production.db")
    sql_runner = SqliteRunner(db_path)
    tool_registry.register(RunSqlTool(sql_runner))

    # 5. Agent 配置
    config = AgentConfig(
        max_tool_iterations=15,  # 更多工具调用次数
        auto_save_conversations=True,
        temperature=0.1,
        max_tokens=8000,
        stream_responses=True,
        ui_features=UiFeatureConfig(
            feature_group_access={
                UiFeature.UI_FEATURE_SHOW_TOOL_NAMES: ["admin"],
                UiFeature.UI_FEATURE_SHOW_TOOL_ARGUMENTS: ["admin", "developer"],
                UiFeature.UI_FEATURE_SHOW_TOOL_ERROR: ["admin"],
                UiFeature.UI_FEATURE_SHOW_MEMORY_DETAILED_RESULTS: ["admin"],
            }
        ),
    )

    # 6. 创建 Agent
    agent = Agent(
        llm_service=AnthropicLlmService(api_key=os.getenv("ANTHROPIC_API_KEY")),
        tool_registry=tool_registry,
        user_resolver=ProductionUserResolver(),
        agent_memory=PersistentAgentMemory(),
        config=config,
        error_recovery_strategy=recovery_strategy,  # 策略配置
        observability_provider=observability,        # 可观测性
        audit_logger=FileAuditLogger("./audit.log"),  # 审计日志
        lifecycle_hooks=[QuotaCheckHook(), RateLimitHook()],
    )

    return agent
```

---

## 配置建议和最佳实践

### 1. 根据场景选择策略

| 场景 | 推荐策略 | 原因 | 配置示例 |
|------|---------|------|---------|
| 开发/测试 | 指数退避 | 快速发现问题 | `max_retries=1-2` |
| 生产环境 | 组合策略 | 兼顾可靠性和用户体验 | 指数退避 + 智能 SQL |
| 内部分析 | 指数退避 | 保证数据准确性 | `max_retries=3-5` |
| 客户查询 | 优雅降级 | 保证基本可用性 | 降级优先 |
| SQL 分析 | 智能 SQL | 区分错误类型 | 语法错误不重试 |

### 2. 错误分类建议

#### 可重试错误（Retryable）

```python
RETRYABLE_ERRORS = {
    # 网络相关
    TimeoutError,
    ConnectionError,
    OSError,  # 包括网络错误

    # 数据库相关
    "connection",
    "timeout",
    "network",
    "unreachable",
    "refused",
    "reset",
    "broken pipe",
    "ssl",

    # API 限流
    "rate limit",
    "too many requests",
    "service unavailable",
    "temporarily unavailable",
}
```

#### 不可重试错误（Non-Retryable）

```python
NON_RETRYABLE_ERRORS = {
    # 代码错误
    ValueError,
    TypeError,
    AttributeError,
    KeyError,

    # SQL 语法错误
    "syntax error",
    "syntax_error",
    "invalid sql",
    "sql syntax",
    "incorrect syntax",

    # 权限错误
    "permission denied",
    "access denied",
    "unauthorized",
    "forbidden",
    "insufficient privilege",

    # 数据错误
    "constraint",
    "foreign key",
    "duplicate key",
    "unique constraint",
}
```

### 3. 指数退避配置

#### 不同场景下的配置建议

```python
# 1. 激进模式（快速失败，适用于开发）
fast_fail = ExponentialBackoffStrategy(
    max_retries=2,
    initial_delay_ms=500,
    max_delay_ms=2000,
)

# 2. 保守模式（确保成功率，适用于关键业务）
reliable = ExponentialBackoffStrategy(
    max_retries=5,
    initial_delay_ms=1000,
    max_delay_ms=30000,  # 最大 30 秒
)

# 3. 平衡模式（推荐）
balanced = ExponentialBackoffStrategy(
    max_retries=3,
    initial_delay_ms=1000,
    max_delay_ms=10000,  # 最大 10 秒
)

# 4. API 限流专用
rate_limit = ExponentialBackoffStrategy(
    max_retries=10,
    initial_delay_ms=1000,
    max_delay_ms=60000,  # 最大 60 秒
    retryable_errors=(RateLimitError, TooManyRequestsError),
)

# 5. 数据库连接专用
db_connection = ExponentialBackoffStrategy(
    max_retries=5,
    initial_delay_ms=500,  # 快速重试
    max_delay_ms=5000,
    retryable_errors=(ConnectionError, TimeoutError, OperationalError),
)
```

#### 延迟时间计算示例

```python
# 配置：initial_delay_ms=1000
attempt 1: delay = 1000ms ± 25% = 750-1250ms
attempt 2: delay = 2000ms ± 25% = 1500-2500ms
attempt 3: delay = 4000ms ± 25% = 3000-5000ms
attempt 4: min(delay, max_delay) = 7000ms (如果 max_delay=10000)
attempt 5: min(delay, max_delay) = 10000ms (如果 max_delay=10000)
```

### 4. 监控和指标

#### 重试监控类

```python
class MonitoredExponentialBackoff(ExponentialBackoffStrategy):
    """带监控的指数退避策略"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = {
            "total_attempts": 0,        # 总尝试次数
            "successful_retries": 0,    # 成功重试次数
            "failed_retries": 0,        # 失败重试次数
            "retry_delays": [],         # 重试延迟记录
            "errors_by_type": {},       # 按类型分类的错误
        }

    def _record_error(self, error: Exception):
        """记录错误类型"""
        error_type = type(error).__name__
        self.metrics["errors_by_type"][error_type] = (
            self.metrics["errors_by_type"].get(error_type, 0) + 1
        )

    async def handle_tool_error(self, error, context, attempt):
        self.metrics["total_attempts"] += 1
        self._record_error(error)

        action = await super().handle_tool_error(error, context, attempt)

        if action.action == RecoveryActionType.RETRY:
            self.metrics["retry_delays"].append(action.retry_delay_ms)
        elif attempt > 1 and action.action == RecoveryActionType.FAIL:
            self.metrics["failed_retries"] += 1
        elif attempt > 1 and action.action != RecoveryActionType.RETRY:
            self.metrics["successful_retries"] += 1

        return action

    def print_metrics(self):
        """打印监控指标"""
        print("\n" + "=" * 80)
        print("RETRY STRATEGY METRICS")
        print("=" * 80)

        print(f"Total attempts:        {self.metrics['total_attempts']}")
        print(f"Successful retries:    {self.metrics['successful_retries']}")
        print(f"Failed retries:        {self.metrics['failed_retries']}")

        if self.metrics["retry_delays"]:
            avg_delay = sum(self.metrics["retry_delays"]) / len(self.metrics["retry_delays"])
            print(f"Average retry delay:   {avg_delay:.0f}ms")
            print(f"Min retry delay:       {min(self.metrics['retry_delays'])}ms")
            print(f"Max retry delay:       {max(self.metrics['retry_delays'])}ms")

        print("\nError types:")
        for error_type, count in sorted(
            self.metrics["errors_by_type"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {error_type}: {count}")

        # 成功率
        if self.metrics["total_attempts"] > 0:
            success_rate = (
                self.metrics["successful_retries"] / self.metrics["total_attempts"] * 100
            )
            print(f"\nSuccess rate:          {success_rate:.1f}%")

        print("=" * 80)
```

#### 与 Prometheus 集成

```python
from prometheus_client import Counter, Histogram, Gauge
import time

# 定义指标
retry_attempts = Counter(
    'vanna_retry_attempts_total',
    'Total number of retry attempts',
    ['tool', 'error_type', 'outcome']
)

retry_delays = Histogram(
    'vanna_retry_delays_ms',
    'Retry delay times in milliseconds',
    ['tool']
)

retry_success_rate = Gauge(
    'vanna_retry_success_rate',
    'Success rate of retries (0.0-1.0)'
)

class PrometheusMonitoredBackoff(ExponentialBackoffStrategy):
    """集成 Prometheus 监控的指数退避策略"""

    async def handle_tool_error(self, error, context, attempt):
        error_type = type(error).__name__
        tool_name = context.metadata.get('tool_name', 'unknown')

        action = await super().handle_tool_error(error, context, attempt)

        # 记录指标
        if action.action == RecoveryActionType.RETRY:
            retry_attempts.labels(
                tool=tool_name,
                error_type=error_type,
                outcome='retry'
            ).inc()

        elif action.action == RecoveryActionType.FAIL:
            if attempt > 1:
                retry_attempts.labels(
                    tool=tool_name,
                    error_type=error_type,
                    outcome='failed_after_retry'
                ).inc()
            else:
                retry_attempts.labels(
                    tool=tool_name,
                    error_type=error_type,
                    outcome='failed_without_retry'
                ).inc()

        return action
```

### 5. 策略组合建议

#### 通用组合（推荐）

```python
# 用于大多数场景
composite_strategy = CompositeErrorStrategy(
    strategies=[
        # 1. 优先尝试指数退避（处理网络/连接问题）
        ExponentialBackoffStrategy(
            max_retries=3,
            initial_delay_ms=1000,
            max_delay_ms=10000,
        ),
        # 2. 智能 SQL 处理（专门处理 SQL 相关错误）
        SmartSqlErrorStrategy(max_retries=2),
        # 3. 优雅降级（确保基本可用性）
        GracefulDegradationStrategy(),
    ]
)
```

#### 生产环境组合

```python
# 用于生产环境，注重稳定性
production_strategy = CompositeErrorStrategy(
    strategies=[
        MonitoredExponentialBackoff(
            max_retries=5,
            initial_delay_ms=500,  # 快速重试
            max_delay_ms=30000,
        ),
        SmartSqlErrorStrategy(max_retries=2),
        GracefulDegradationStrategy(enable_fallbacks=True),
    ]
)
```

#### 分析场景组合

```python
# 用于数据分析，注重准确性
analytical_strategy = CompositeErrorStrategy(
    strategies=[
        ExponentialBackoffStrategy(
            max_retries=3,
            retryable_errors=(ConnectionError, TimeoutError),
            # 不自动重试其他错误，让 LLM 修正
        ),
        SmartSqlErrorStrategy(max_retries=1),  # 仅一次重试
    ]
)
```

---

## 常见问题和解决方案

### Q1: 重试会阻塞 Agent 吗？

**回答：不会阻塞。**

```python
try:
    result = await tool.execute(context, args)  # 异步执行
except Exception as e:
    if action.retry_delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)  # 非阻塞延迟
    # 继续重试
```

Vanna 使用 `async/await` 异步执行，重试期间的 `sleep` 是非阻塞的，Agent 可以同时处理其他请求。

### Q2: 如何测试重试逻辑？

#### 单元测试

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch


class FailingTool:
    """模拟会失败的工具"""

    def __init__(self, fail_times=2):
        self.fail_times = fail_times
        self.calls = 0

    async def execute(self, context, args):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError(f"Simulated error (call {self.calls})")
        return ToolResult(success=True, result_for_llm="Success on retry")

    def get_schema(self):
        return {}


@pytest.mark.asyncio
async def test_retry_success():
    """测试重试最终成功"""
    tool = FailingTool(fail_times=2)
    strategy = ExponentialBackoffStrategy(max_retries=3)

    # 模拟工具调用
    context = ToolContext(
        user=User(id="test", name="Test User", group_memberships=[]),
        conversation_id="test_001",
        request_id="req_001",
        metadata={},
    )

    # 重试直到成功
    result = None
    last_error = None

    for attempt in range(1, 4):
        try:
            result = await tool.execute(context, {})
            break
        except Exception as e:
            last_error = e
            action = await strategy.handle_tool_error(e, context, attempt)

            if action.action != RecoveryActionType.RETRY:
                break

            if action.retry_delay_ms > 0:
                await asyncio.sleep(action.retry_delay_ms / 1000.0)

    # 断言
    assert result is not None
    assert result.success is True
    assert tool.calls == 3  # 2 次失败 + 1 次成功


@pytest.mark.asyncio
async def test_retry_exhausted():
    """测试重试次数耗尽"""
    tool = FailingTool(fail_times=5)  # 失败次数超过重试次数
    strategy = ExponentialBackoffStrategy(max_retries=3)

    context = ToolContext(
        user=User(id="test", name="Test User", group_memberships=[]),
        conversation_id="test_002",
        request_id="req_002",
        metadata={},
    )

    # 尝试执行
    result = None
    last_error = None

    for attempt in range(1, 4):
        try:
            result = await tool.execute(context, {})
            break
        except Exception as e:
            last_error = e
            action = await strategy.handle_tool_error(e, context, attempt)

            if action.action != RecoveryActionType.RETRY:
                assert action.action == RecoveryActionType.FAIL
                break

            if action.retry_delay_ms > 0:
                await asyncio.sleep(action.retry_delay_ms / 1000.0)

    # 断言
    assert result is None
    assert tool.calls == 3  # 只尝试了 3 次


@pytest.mark.asyncio
async def test_non_retryable_error():
    """测试不可重试错误"""
    tool = AsyncMock()
    tool.execute = AsyncMock(side_effect=ValueError("Invalid argument"))

    strategy = ExponentialBackoffStrategy()
    context = ToolContext(
        user=User(id="test", name="Test User", group_memberships=[]),
        conversation_id="test_003",
        request_id="req_003",
        metadata={},
    )

    # 第一次尝试
    with pytest.raises(ValueError):
        await tool.execute(context, {})

    # 策略应该建议失败
    action = await strategy.handle_tool_error(
        ValueError("Invalid argument"), context, attempt=1
    )

    assert action.action == RecoveryActionType.FAIL
    assert "Non-retryable" in action.message
```

#### 集成测试

```python
@pytest.mark.asyncio
async def test_retryable_tool_registry():
    """测试 RetryableToolRegistry"""

    # 创建模拟工具
    mock_tool = AsyncMock()
    mock_tool.name = "test_tool"
    mock_tool.execute = AsyncMock(side_effect=[
        ConnectionError("Network error"),
        ConnectionError("Network error"),
        ToolResult(success=True, result_for_llm="Success"),
    ])

    # 创建注册表
    strategy = ExponentialBackoffStrategy(max_retries=3)
    registry = RetryableToolRegistry(error_recovery_strategy=strategy)

    # 注册工具
    registry._tools["test_tool"] = mock_tool

    # 模拟工具调用
    tool_call = ToolCall(id="call_001", name="test_tool", arguments={})
    context = ToolContext(
        user=User(id="test", name="Test User", group_memberships=[]),
        conversation_id="test_001",
        request_id="req_001",
        metadata={},
    )

    # 执行（应该自动重试）
    result = await registry.execute(tool_call, context)

    # 断言
    assert result.success is True
    assert result.result_for_llm == "Success"
    assert mock_tool.execute.call_count == 3
```

### Q3: 如何让 LLM 知道发生了重试？

#### 方案 1：更新上下文元数据

```python
class InformativeRetryStrategy(ExponentialBackoffStrategy):
    """通知 LLM 重试的策略"""

    async def handle_tool_error(self, error, context, attempt):
        action = await super().handle_tool_error(error, context, attempt)

        # 在重试时更新上下文元数据
        if action.action == RecoveryActionType.RETRY and attempt > 1:
            if context.metadata is None:
                context.metadata = {}

            context.metadata["retry_info"] = {
                "attempt": attempt,
                "previous_error": str(error),
                "error_type": type(error).__name__,
                "next_retry_delay_ms": action.retry_delay_ms,
                "total_retries": attempt - 1,
            }

            # 添加说明到消息
            action.message = (
                f"[Retry {attempt}] Previous attempt failed with: {str(error)}. "
                f"Retrying after {action.retry_delay_ms}ms..."
            )

        return action
```

#### 方案 2：修改系统提示

```python
class RetryAwareLlmContextEnhancer(LlmContextEnhancer):
    """感知重试的 LLM 上下文增强器"""

    async def enhance_system_prompt(self, prompt, message, user):
        """在系统提示中添加重试处理说明"""

        retry_instructions = """

## Retry Handling

If a tool fails and is being retried:
1. Pay attention to the error message from previous attempts
2. If it's a syntax error, fix the SQL/query before retrying
3. If it's a connection error, the system will handle it automatically
4. If it fails after multiple retries, suggest alternative approaches
5. For timeout errors, suggest simplifying the query (add LIMIT, reduce date range)

Previous retry information (if any) is in the context metadata.
"""

        return prompt + retry_instructions

    async def enhance_user_messages(self, messages, user):
        """在用户消息中添加重试上下文"""
        # 不需要修改用户消息
        return messages
```

#### 方案 3：在对话历史中记录

```python
class ConversationRecordingStrategy(ExponentialBackoffStrategy):
    """在对话历史中记录重试的策略"""

    async def handle_tool_error(self, error, context, attempt):
        action = await super().handle_tool_error(error, context, attempt)

        # 记录到 Agent 内存（如果可用）
        if hasattr(context, "agent_memory") and context.agent_memory:
            try:
                await context.agent_memory.save_tool_usage(
                    question=f"Retry attempt {attempt}",
                    tool_name=context.metadata.get("tool_name", "unknown"),
                    args={
                        "error": str(error),
                        "error_type": type(error).__name__,
                        "attempt": attempt,
                        "action": action.action,
                    },
                    context=context,
                    success=False,  # 记录为失败尝试
                )
            except Exception as e:
                logger.warning(f"Failed to record retry to memory: {e}")

        return action
```

### Q4: 重试 vs LLM 自动修正，如何配合？

这两者可以**结合使用**，形成完整的错误处理链：

#### 工作流程

```
用户提问
   ↓
1. Agent 生成 SQL
   ↓
2. 执行 SQL
   ├─ 成功 → 返回结果
   └─ 失败
      ↓
3. ErrorRecoveryStrategy 处理
   ├─ 网络/连接错误 → RETRY（等待后重试）
   ├─ 语法/表不存在错误 → FAIL（不重试）
   └─ 超时 → FAIL（建议简化）
      ↓
4. 如果是 FAIL
   ↓
5. LLM 看到错误信息
   ↓
6. LLM 分析错误
   ├─ 语法错误 → 修正 SQL
   ├─ 表不存在 → 查询 schema 或询问用户
   ├─ 数据问题 → 调整查询条件
   └─ 其他 → 提供替代方案
   ↓
7. LLM 生成修正后的 SQL
   ↓
8. 再次执行（可能再次触发重试机制）
   ↓
9. 返回最终结果
```

#### 代码示例：结合重试和 LLM 修正

```python
async def execute_with_retry_and_llm_fix(agent, tool_call, context):
    """结合重试和 LLM 修正"""

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            # 尝试执行工具
            result = await agent.tool_registry.execute(tool_call, context)

            if result.success:
                return result

            # 工具返回失败（不是抛出异常）
            error_msg = result.error or result.result_for_llm

        except Exception as e:
            error_msg = str(e)

        # 判断错误类型
        if any(keyword in error_msg.lower() for keyword in [
            "syntax", "does not exist", "invalid"
        ]):
            # SQL 语法/表不存在错误 → 不重试，让 LLM 修正
            if attempt == 1:
                return ToolResult(
                    success=False,
                    result_for_llm=(
                        f"SQL Error: {error_msg}\n\n"
                        "The SQL query has an error. Please:\n"
                        "1. Check table and column names\n"
                        "2. Verify syntax is correct\n"
                        "3. Consider simplifying the query"
                    ),
                    error=error_msg,
                )
            else:
                #已经尝试过LLM修正，仍然失败
                return ToolResult(
                    success=False,
                    result_for_llm=f"SQL Error persists after correction: {error_msg}",
                    error=error_msg,
                )

        elif any(keyword in error_msg.lower() for keyword in [
            "connection", "timeout", "network"
        ]):
            # 网络/连接错误 → 重试
            if attempt < max_attempts:
                delay_ms = min(1000 * (2  ** (attempt - 1)), 10000)
                logger.info(f"Retrying after {delay_ms}ms (attempt {attempt})")
                await asyncio.sleep(delay_ms / 1000.0)
                continue

            # 重试次数耗尽
            return ToolResult(
                success=False,
                result_for_llm=f"Connection failed after {max_attempts} attempts: {error_msg}",
                error=error_msg,
            )

        else:
            # 其他错误 → 不重试
            return ToolResult(
                success=False,
                result_for_llm=error_msg,
                error=error_msg,
            )

    # 意外情况
    return ToolResult(
        success=False,
        result_for_llm="Unexpected retry loop exit",
        error="Max retry attempts exceeded",
    )
```

#### 典型场景示例

**场景 1：网络连接问题**

```python
# 第 1 次尝试：连接超时
Error: Connection timeout after 30s
Action: RETRY (等待 2 秒)

# 第 2 次尝试：连接成功，执行成功
Result: Success
```

**  场景 2：SQL 语法错误**

```python
# 第 1 次尝试：语法错误
Error: syntax error at or near "SELCT"
Action: FAIL（不重试，返回给 LLM）

# LLM 看到错误："SELCT" → 修正为 "SELECT"

# 第 2 次尝试：修正后的 SQL
Result: Success
```

**场景 3：表不存在**（需要 LLM 介入）

```python
# 第 1 次尝试：表不存在
Error: relation "user_data" does not exist
Action: FAIL（不重试，返回给 LLM）

# LLM 查询 schema，发现表名是 "users"
# LLM 修正 SQL

# 第 2 次尝试：使用正确的表名
Result: Success
```

**场景 4：查询超时**（需要调整查询）

```python
# 第 1 次尝试：查询超时
Error: Query timeout after 60s
Action: FAIL（不重试，返回给 LLM）

# LLM 看到超时错误，添加 LIMIT 1000，减少时间范围

# 第 2 次尝试：简化后的查询
Result: Success
```

### Q5: 如何防止无限重试？

#### 1. 配置最大重试次数

```python
strategy = ExponentialBackoffStrategy(
    max_retries=3,  # 明确限制
    # ...
)
```

#### 2. 总超时限制

```python
import asyncio

async def execute_with_timeout(tool, context, args, timeout=60):
    """带总超时的执行"""

    try:
        return await asyncio.wait_for(
            tool.execute(context, args),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        return ToolResult(
            success=False,
            result_for_llm="Query exceeded maximum execution time",
            error="Total timeout",
        )
```

#### 3. 熔断器模式（Circuit Breaker）

```python
class CircuitBreaker:
    """熔断器，防止持续调用失败的工具"""

    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def can_execute(self):
        """检查是否可以执行"""

        if self.state == "OPEN":
            # 检查是否可以切换到 HALF_OPEN
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                return True
            return False

        return True

    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(f"Circuit breaker OPENED for tool")


class CircuitBreakerToolRegistry(RetryableToolRegistry):
    """集成熔断器的工具注册表"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.circuit_breakers = {}  # tool_name -> CircuitBreaker

    async def execute(self, tool_call, context):
        tool_name = tool_call.name

        # 获取或创建熔断器
        if tool_name not in self.circuit_breakers:
            self.circuit_breakers[tool_name] = CircuitBreaker()

        circuit_breaker = self.circuit_breakers[tool_name]

        # 检查熔断器状态
        if not circuit_breaker.can_execute():
            return ToolResult(
                success=False,
                result_for_llm=(
                    f"Tool '{tool_name}' is currently unavailable due to repeated failures. "
                    "Please try again later or contact support."
                ),
                error="Circuit breaker is OPEN",
            )

        # 执行工具
        result = await super().execute(tool_call, context)

        # 更新熔断器状态
        if result.success:
            circuit_breaker.record_success()
        else:
            circuit_breaker.record_failure()

        return result
```

---

## 总结

### 1. 关键点回顾

- ** ErrorRecoveryStrategy 是一个设计完善的扩展点，但尚未完全集成到 Vanna 2.0 核心执行流程中 **
- ** 目前可用的解决方案是创建自定义的 RetryableToolRegistry **
- ** 提供了多种策略：指数退避、智能 SQL、优雅降级、组合策略 **
- ** 重试机制与 LLM 自动修正可以结合使用，形成完整的错误处理链 **

### 2. 推荐配置

#### 开发环境

```python
agent = Agent(
    tool_registry=RetryableToolRegistry(
        error_recovery_strategy=ExponentialBackoffStrategy(
            max_retries=2,
            initial_delay_ms=500,
        )
    ),
    # ... 其他配置
)
```

#### 生产环境

```python
agent = Agent(
    tool_registry=RetryableToolRegistry(
        error_recovery_strategy=CompositeErrorStrategy(
            strategies=[
                MonitoredExponentialBackoff(max_retries=5),
                SmartSqlErrorStrategy(max_retries=2),
                GracefulDegradationStrategy(),
            ]
        )
    ),
    observability_provider=LoggingObservabilityProvider(),
    # ... 其他配置
)
```

#### 分析场景

```python
agent = Agent(
    tool_registry=RetryableToolRegistry(
        error_recovery_strategy=SmartSqlErrorStrategy(max_retries=2)
    ),
    # ... 其他配置
)
```

### 3. 未来展望

在 Vanna 的未来版本中，我们预期：

1. **官方集成**: ErrorRecoveryStrategy 直接集成到 ToolRegistry
2. **更多内置策略**: 提供开箱即用的常用策略
3. **更强的可观测性**: 内置重试指标和监控
4. **LLM 协同优化**: 更好地结合重试和 LLM 自动修正
5. **可视化界面**: 在 UI 中显示重试状态和原因

### 4. 参考资料

- **核心源码**:
  - `src/vanna/core/recovery/base.py`: 策略接口
  - `src/vanna/core/recovery/models.py`: 数据模型
  - `src/vanna/core/agent/agent.py`: Agent 集成
  - `src/vanna/core/registry.py`: 工具执行
  - `src/vanna/examples/extensibility_example.py`: 示例实现

- **相关概念**:
  - [指数退避算法](https://en.wikipedia.org/wiki/Exponential_backoff)
  - [熔断器模式](https://martinfowler.com/bliki/CircuitBreaker.html)
  - [重试模式](https://docs.microsoft.com/en-us/azure/architecture/patterns/retry)

---

## 附录：完整代码清单

### A. 核心文件

1. **`RetryableToolRegistry`** - 支持重试的工具注册表
2. **`ExponentialBackoffStrategy`** - 指数退避策略
3. **`SmartSqlErrorStrategy`** - 智能 SQL 错误处理
4. **`GracefulDegradationStrategy`** - 优雅降级策略
5. **`CompositeErrorStrategy`** - 组合策略
6. **`MonitoredExponentialBackoff`** - 带监控的策略

### B. 使用示例

1. **基础使用** - 简单的 Agent 配置
2. **生产环境** - 完整的生产配置
3. **监控集成** - 与 Prometheus 集成
4. **测试示例** - 单元测试和集成测试

### C. 最佳实践

1. 错误分类指南
2. 配置参数选择
3. 策略组合建议
4. 性能优化建议

---

** 讨论结束 **

如果您有任何问题或建议，请提交 Issue 或联系维护团队。

---

** 文档信息 **

- 创建时间: 2025-12-12
- 最后更新: 2025-12-12
- 版本: 1.0
- 状态: 活跃讨论
- 相关 Issue: [如有]
