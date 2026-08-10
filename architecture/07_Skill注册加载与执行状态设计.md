# Skill 注册、加载与执行状态设计

> 文档编号：07  
> 目标：定义 Skill 与 Tool 的边界、Skill 的轻量注册、按需加载、执行状态和压缩策略。

---

## 1. Skill 定义

Skill 是：

> 面向一个业务目标的可复用任务方法、工作流和操作规范。

例如：

```text
production_scheduling
shortage_analysis
schedule_explanation
schedule_publish
```

Skill 可以描述：

- 适用场景
- 任务步骤
- 决策原则
- 需要调用的 Tool 类型
- 验证条件
- 停止条件
- 输出规范

---

## 2. Skill 与 Tool 的区别

```text
Tool
= 能做一个动作

Skill
= 如何组织多个动作完成一个任务
```

例如：

```text
Skill: shortage_analysis
    ├─ query_order
    ├─ query_bom
    ├─ query_inventory
    └─ summarize_shortage
```

---

## 3. Prefix 中只放 Skill Index

推荐：

```yaml
skills:
  - skill_id: production_scheduling
    name: 生产排产
    description: 根据订单、物料、设备和工艺约束完成端到端排产

  - skill_id: shortage_analysis
    name: 缺料分析
    description: 分析订单物料齐套与缺料风险
```

不放完整 Skill Body。

---

## 4. Skill Store

```python
class SkillDescriptor:
    skill_id: str
    name: str
    description: str
    version: str
```

```python
class SkillDefinition:
    descriptor: SkillDescriptor
    body: str
```

Skill Store 保存：

- body
- version
- hash
- estimated_tokens
- dependencies
- metadata

---

## 5. Skill Loading

```text
User Task
   ↓
Agent判断某 Skill 合适
   ↓
load_skill(skill_id)
   ↓
SkillResolver
   ↓
完整 Skill Body
   ↓
当前 Working Context
```

如果 Skill 已经通过当前 Checkpoint 标记为 active：

```text
active_skill.id
```

SkillResolver 可以自动重新加载，不要求模型再次搜索。

---

## 6. Skill Event

第一版建议只保留：

```text
SKILL_ACTIVATED
```

示例：

```json
{
  "event_type": "SKILL_ACTIVATED",
  "payload": {
    "skill_id": "production_scheduling",
    "version": "2.3"
  }
}
```

不记录 Skill Body。

Skill 步骤变化通过：

```text
PLAN_STEP_UPDATED
```

管理，而不是为 Skill 单独发几十种事件。

---

## 7. Skill 与 PlanManager

Skill 是模板；Plan 是当前实例。

例如 Skill：

```text
1. 获取订单
2. 检查BOM
3. 检查库存
4. 获取设备
5. 求解
6. 确认
7. 下发
```

激活后生成 Plan：

```text
PLAN-A1001

T1 order_info
T2 bom_check
T3 inventory_check
...
```

因此：

```text
Skill Definition
   ↓ instantiate
Plan
   ↓ execute
Events
```

Skill 本身不需要保存当前任务动态状态。

---

## 8. Skill 当前状态

Checkpoint 保存：

```yaml
active_skill:
  id: production_scheduling
  version: "2.3"
  current_phase: optimization

plan_state:
  plan_id: PLAN-A1001
  completed_milestones:
    - data_ready
    - constraints_validated
  pending_milestones:
    - schedule_confirmation
    - schedule_publish
```

完整 TODO 在 PlanManager。

---

## 9. Skill 压缩

原则：

> Skill 定义不压缩，Skill 执行状态才压缩。

Compact：

```text
Skill Body
→ DROP / Reloadable

Skill ID + Version
→ 必要时保留

Skill Execution Progress
→ 以 Plan / milestone 形式保留
```

后续需要继续执行：

```text
Checkpoint.active_skill
       ↓
SkillResolver
       ↓
重新加载 Skill Body
```

---

## 10. Skill Version

Session 中一旦激活：

```text
production_scheduling@2.3
```

应在该执行实例中保持版本稳定。

如果要切到 v2.4：

- 显式产生变更
- 必要时生成新 Plan
- 评估旧状态是否兼容
- 记录审计

避免进行到一半 Skill 逻辑静默变化。

---

## 11. Skill 与 Tool Lazy Loading

Skill Body 不应要求预加载所有 Tool Schema。

Skill 可以写：

```text
需要：订单查询能力
需要：库存查询能力
需要：排程求解能力
```

Runtime/Agent 根据执行阶段：

```text
Tool Search
→ 加载真正需要的 Tool
```

这样 Skill 不与某一个固定 MCP 接口强耦合。

---

## 12. Skill 的设计建议

Skill 应尽量描述“业务能力步骤”，不要硬编码过细接口编排：

不推荐：

```text
调用接口A
拿字段X
再调用接口B
再调用接口C
```

推荐：

```text
获取订单生产需求
检查物料齐套
确认候选资源
执行排程求解
```

具体 Tool 由 Capability Resolver 决定。

这样接口变更不会导致 Skill 大量重写。

---

## 13. Skill 内容结构建议

```markdown
# Skill Name

## 适用场景

## 输入

## 目标

## 前置条件

## 推荐步骤

## 关键约束

## 可使用能力类型

## 失败与重试原则

## 需要用户确认的动作

## 完成条件

## 输出要求
```

---

## 14. Skill 与 Checkpoint 的边界

Checkpoint 不保存：

- Skill 完整说明
- Skill 的所有示例
- Skill 的 Tool Schema
- Skill 的历史旧版本正文

Checkpoint 保存：

- active skill id/version
- 当前 phase
- 当前任务已形成的业务状态
- plan milestones

---

## 15. 第一版验收

- Prefix 中 Skill 只占轻量目录。
- Skill Body 能按需加载。
- Skill 激活后可生成 Plan。
- Compact 后仍可通过 `active_skill` 继续。
- Skill Version 可追溯。
- Skill 不依赖固定细粒度接口序列。
