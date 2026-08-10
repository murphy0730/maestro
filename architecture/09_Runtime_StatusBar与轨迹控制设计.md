# Agent Runtime Status Bar 与轨迹控制设计

> 文档编号：09  
> 目标：在每轮 Context 末尾提供极小的当前控制状态，减少 Goal Drift、Tool Loop、约束遗忘和错误副作用操作。

---

## 1. 定位

Status Bar 不是历史摘要。

它回答：

```text
我现在要完成什么？
我现在做到哪里？
下一步应该做什么？
当前有什么阻塞或异常？
现在能不能执行关键动作？
```

---

## 2. Context 位置

```text
Immutable Prefix
Latest Checkpoint
Recent Events
Runtime Status Bar  ← 永远最后
```

它是“当前注意力投影”。

---

## 3. 第一版字段

建议只实现：

```yaml
goal:
current_step:
next_action:
blockers:
critical_constraints:
alerts:
execution_gate:
```

正常情况下只出现有内容的字段。

---

## 4. 示例

```yaml
<agent_state>
goal: 完成订单A1001排产

current_step: 生成候选排程
next_action: 调用排程求解能力

blockers:
  - M03设备状态已过期

critical_constraints:
  - 产品X禁止使用M01

execution_gate:
  publish_schedule: blocked
  reason: 等待用户确认

alerts:
  - query_inventory同参数已调用3次
</agent_state>
```

---

## 5. Token 约束

目标：

```text
正常：100~500 tokens
硬上限：800 tokens
```

不要加入：

- 全量历史
- 全量 TODO
- 全量约束
- 所有 Tool 调用统计
- 所有 freshness
- 所有时间侧信道

Status Bar 必须“稀疏”。

---

## 6. 信息生命周期

Status 字段分三类：

### Durable State

例如：

```text
goal
关键约束背后的事实
用户确认状态
```

Source of Truth 在 Checkpoint/Event/Plan。

### Derived State

例如：

```text
current_step
next_action
execution_gate
```

由 PlanManager/规则重新计算。

### Ephemeral Signal

例如：

```text
repeated_tool_call
no_progress
stale_data warning
```

问题消失后直接消失。

---

## 7. Status Bar 不进入 Checkpoint

Compact 时：

```text
Old Status Bar
→ DROP
```

下一轮：

```text
Checkpoint
+
Hot Events
+
Plan State
+
Runtime Metrics
        ↓
StatusBarBuilder
        ↓
New Status Bar
```

因此 Status Bar 自身不会积累。

---

## 8. Plan Projection

完整 Plan：

```text
T1...T30
```

存在 PlanManager。

Status 只展示：

```yaml
goal: ...
current_step: T15 ...
next_action: T16 ...
```

必要时加：

```yaml
progress: 14/30
```

但不建议默认每轮展示全量 TODO。

---

## 9. Critical Constraints

Checkpoint 可以有 20 个约束。

Status 只选择当前步骤最可能违反的 1～3 个：

当前在设备选择：

```text
产品X禁止M01
```

当前在下发：

```text
未经用户确认不得下发
```

这是一种有目的的重复，用于提升可靠性。

---

## 10. Alerts

采用 exception-only。

正常：

```text
不输出 alerts
```

异常时：

```yaml
alerts:
  - query_inventory同参数已调用3次
  - 连续6个Agent Step无状态推进
```

---

## 11. TrajectoryMonitor

推荐独立模块：

```python
class TrajectoryMonitor:
    def detect_repeated_tool_call(...):
        ...

    def detect_no_progress(...):
        ...

    def detect_repeated_failure(...):
        ...

    def detect_stale_dependency(...):
        ...
```

程序化检测，不依赖 LLM 自评。

---

## 12. No Progress

定义“进展”可以包括：

- Plan Step 完成
- 新有效 Fact
- 新 Constraint
- Blocker 被解除
- 新 Decision
- 用户确认
- Tool 获取了必要信息

如果连续 N Step 都没有这些变化：

```text
no_progress
```

向 Status 投影提醒。

N 需要 Eval 调整。

---

## 13. Data Freshness

Runtime 内部维护：

```yaml
machine_status:
  observed_at:
  ttl:
```

正常 fresh 不显示。

过期才：

```yaml
blockers:
  - M03实时状态已过期，需要重新查询
```

避免每轮输出完整 freshness 表。

---

## 14. Execution Gate

排产 Agent 需要明确控制副作用。

例如：

```yaml
execution_gate:
  publish_schedule: blocked
  reason: user_confirmation_missing
```

底层计算：

```text
System Rule:
publish需要确认

Session State:
confirmation=false

→ Runtime:
blocked
```

不要让 LLM 自己推断权限。

---

## 15. 时间与位置 Side Channel

不默认输出。

只有语义相关时：

```text
用户两天后回来继续排产
→ 提醒实时状态可能过期

用户问“明天”
→ 注入当前时间/时区
```

地理位置只有影响：

- 时区
- 工厂
- 物流
- 地方法规

时才注入。

---

## 16. StatusBarBuilder

```python
class StatusBarBuilder:

    def build(self, session_id):
        return {
            "goal": plan_manager.goal(session_id),
            "current_step": plan_manager.current_step(session_id),
            "next_action": plan_manager.next_action(session_id),
            "blockers": blocker_resolver.current(session_id),
            "critical_constraints": constraint_projector.select(session_id),
            "alerts": trajectory_monitor.alerts(session_id),
            "execution_gate": permission_manager.current_gate(session_id),
        }
```

---

## 17. 与 Checkpoint 的边界

```text
Checkpoint:
完整有效状态

Status:
当前最需要注意的状态
```

例如 Checkpoint：

```yaml
user_confirmation: false
```

Status：

```yaml
publish_schedule: blocked
```

Checkpoint 保存事实，Status 保存控制投影。

---

## 18. 性能验证

需要 A/B Eval：

```text
Without Status Bar
vs
With Status Bar
```

比较：

- Goal Drift Rate
- Constraint Violation Rate
- Repeated Tool Call Rate
- No-progress Loop Rate
- Premature Side-effect Rate
- Task Success Rate
- Extra Context Tokens

只有真实提升大于 token 成本，字段才保留。

---

## 19. 第一版原则

Status Bar 应该像汽车仪表盘：

- 当前速度
- 关键告警
- 下一步导航

而不是把整本维修手册贴在仪表盘上。
