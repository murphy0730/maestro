# Tool / MCP 能力发现与懒加载设计

> 文档编号：06  
> 目标：在大量 MES、ERP、WMS、APS Tool 场景下，通过 Tool Search + Lazy Schema Loading 控制 Context，同时保证工具选择准确率。

---

## 1. 设计动机

如果 Agent 拥有几百个 Tool，并把全部完整 JSON Schema 放进 Prefix，会导致：

- Prefix token 过大
- Tool 描述相互干扰
- Tool 选择准确性下降
- Tool Definition 变化影响 Prefix 稳定性
- Prompt Cache 前缀变化
- 大量本轮无关 Schema 浪费窗口

因此采用：

```text
轻量能力目录
+
Tool Search
+
按需加载完整 Schema
```

---

## 2. 概念边界

### MCP

MCP 是 Tool Provider / 接入协议。

```text
MES MCP Server
    ├─ query_order
    ├─ query_machine_status
    └─ publish_schedule
```

Agent 选择的是 Tool，不是“选择 MCP”作为业务动作。

### Tool

可执行能力，具有：

- name
- description
- input schema
- output contract
- provider
- version
- permissions

---

## 3. 两个核心对象

为了避免过度设计，第一版只保留两个核心模型。

### 3.1 ToolDescriptor

轻量发现信息：

```python
class ToolDescriptor:
    tool_id: str
    name: str
    description: str
    namespace: str
    version: str
```

可选增强字段：

```text
aliases
entities
operation_type
side_effect
```

但不要强制第一版全部使用。

### 3.2 ToolDefinition

```python
class ToolDefinition:
    descriptor: ToolDescriptor
    input_schema: dict
```

完整 Schema 存：

```text
Tool Registry / MCP Provider
```

而不是 Event Store 或 Checkpoint。

---

## 4. Prefix 中放什么

推荐只放：

```yaml
tool_namespaces:
  MES:
    description: 生产订单、设备、工单、制造执行相关能力

  ERP:
    description: 订单、BOM、物料、采购相关能力

  WMS:
    description: 库存、库位、出入库、缺料相关能力

  APS:
    description: 排程求解、方案评价、约束检查相关能力
```

以及固定 Meta Tool：

```text
tool_search
```

如果 Tool 总量较少，也可附上部分 `name + description`。

---

## 5. Tool Search 流程

```text
User Task
   ↓
LLM判断需要外部能力
   ↓
tool_search(query, optional namespace)
   ↓
Top-K ToolDescriptor
   ↓
选择目标 Tool
   ↓
Runtime加载完整 ToolDefinition
   ↓
下一次模型调用时提供 callable schema
   ↓
TOOL_CALL
   ↓
TOOL_RESULT
```

核心链路：

```text
SEARCH → LOAD → CALL → RESULT
```

---

## 6. 为什么懒加载可能提高准确率

工具选择变为两阶段：

```text
Stage 1:
Tool Search Recall

Stage 2:
Candidate Selection + Argument Generation
```

大规模 Tool Universe 不再同时暴露给模型。

但新的关键风险是：

> 正确工具没有被 Tool Search 召回。

因此 Tool Search 必须重点优化 Recall@K。

---

## 7. Search Index 应比模型看到的信息更丰富

虽然 Prefix 只展示轻量信息，但 Tool Search 服务内部可索引：

- name
- description
- aliases
- namespace
- entity
- parameter names
- parameter descriptions
- examples
- tags

即：

```text
Search Index
知道完整 Tool 语义

Main Agent
初始不需要看到完整 Schema
```

这解决“省 token”与“搜索准确率”的冲突。

---

## 8. Namespace Routing

不要直接在几百 Tool 中盲搜。

推荐：

```text
Intent
  ↓
Namespace
  ↓
Tool Search
  ↓
Top-K
```

例如：

```text
“为什么订单A缺料？”
     ↓
WMS / ERP
     ↓
query_material_shortage
query_inventory
...
```

Namespace 可以由：

- 规则
- 轻量分类器
- LLM
- 混合策略

决定。

---

## 9. Hybrid Tool Loading

不建议全部 Tool 都 Deferred。

保留少量 Core Tools：

```text
tool_search
get_current_plan
get_referenced_result
```

以及确实高频、稳定、Schema 很小的核心能力。

其余 Long-tail Tool 懒加载。

---

## 10. Runtime 集成

```python
class ToolRegistry:
    def search(self, query, namespace=None, top_k=5):
        ...

    def get_definition(self, tool_id, version=None):
        ...
```

```python
class ToolResolver:
    def resolve(self, session_id, selected_tool_ids):
        return [
            registry.get_definition(tool_id)
            for tool_id in selected_tool_ids
        ]
```

ContextBuilder 不负责 Tool Resolution。

---

## 11. Event 设计

为了保持简单，只记录：

```text
TOOL_SEARCH
TOOL_CALL
TOOL_RESULT
```

### TOOL_SEARCH

记录：

- query
- namespace
- candidates
- selected tool

### TOOL_CALL

记录：

- tool_id
- version
- arguments
- evidence refs

### TOOL_RESULT

记录：

- status
- digest
- result_ref
- latency

**不增加 `TOOL_SCHEMA_LOADED` Event 作为第一版强制结构。**

Schema 加载属于 Runtime 行为，不是必须进入业务轨迹的事实。

---

## 12. Tool Schema 在 Context 中的位置

Schema 不需要当普通 Event 文本长期拼接。

更准确的实现是：

```text
Runtime根据 selected tool
        ↓
获取 ToolDefinition
        ↓
作为 Provider callable tools 参数
        ↓
模型下一次推理可直接调用
```

如果为了可解释性，需要在内部轨迹标记“本轮哪些 Tool 被提供”，可记录轻量 telemetry，但不必进入 LLM Context。

---

## 13. Tool Result

Tool Result 默认：

```text
Raw Result
   ↓
ToolResultStore
```

同时产生：

```text
Digest
+
result_ref
```

进入 Event。

例如：

```yaml
tool_id: query_material_shortage
digest:
  material_ready: false
  shortages:
    - P003
result_ref: result://R123
```

---

## 14. 压缩处理

### TOOL_SEARCH

通常 Drop from Checkpoint。

保留在 Event Store 用于工具选择评估。

### TOOL_CALL

通常不作为独立持久状态。

### TOOL_RESULT

仅将未来相关结果晋升：

```yaml
facts:
  - value: A1001缺少P003
    source:
      tool_id: query_material_shortage
      result_ref: result://R123
```

### Tool Schema

从不进入 Checkpoint。

如果后续还需要该 Tool：

```text
ToolResolver重新加载
```

即可。

---

## 15. 工具选择准确率指标

第一版至少：

```text
Tool Search Recall@K
Tool Selection Accuracy
Tool Argument Accuracy
Unnecessary Tool Call Rate
```

定位方式：

```text
正确 Tool 不在 Top-K
→ Search/Index 问题

正确 Tool 在 Top-K 但选错
→ LLM Selection 问题

Tool 选对但参数错
→ Schema/Prompt/Argument Generation 问题
```

---

## 16. 副作用与权限

ToolDescriptor 建议至少能够标记：

```yaml
operation_type: write
side_effect: high
```

对于：

```text
publish_schedule
cancel_work_order
create_production_order
```

Runtime 在实际执行前检查：

```text
execution_gate
user_confirmation
permission
```

不能只依赖模型自己记住规则。

---

## 17. Version 与 Replay

TOOL_CALL 必须记录：

```text
tool_id
tool_version
```

Replay 时可以恢复当时定义。

Tool Registry 应支持历史 Version，或至少保存：

```text
schema_hash
```

用于审计。

---

## 18. 第一版避免的复杂度

暂不实现：

- UNSEEN / DISCOVERED / ACTIVE / COOLING 状态机
- Tool Schema TTL
- Tool Dependency Graph
- Tool Schema Loaded Event
- Tool 自动长期预热
- 多级 Tool Search Agent

第一版坚持：

```text
Descriptor
Definition
Search
Call
Result
```

---

## 19. 验收标准

- 数百 Tool 不要求全 Schema 常驻。
- Tool Search Recall@5 达到业务目标。
- Tool Schema 不进入 Checkpoint。
- Tool Result 可通过 result_ref 再读取。
- Tool Call 可回溯 Tool Version 和触发原因。
- 副作用 Tool 受到 Runtime Gate 控制。
