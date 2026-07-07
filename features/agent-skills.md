# Agent Skills — 技能模块文档

## 概述

本项目的技能模块允许用户以 `.md` 或 `.zip` 格式导入自定义技能包，扩展调度平台的能力。技能本质上是**封装好的 ReAct 流程**，复用平台现有的 AgentLoop、工具护栏、权限体系，无需修改代码即可新增业务能力。

## 技能文件结构

### 最小示例

一个技能至少需要一个 `SKILL.md` 文件，格式如下：

```markdown
---
name: my-skill
display_name: 我的技能
description: 一句话描述技能用途
when_to_use:
  - 用户会说什么触发这个技能
allowed_tools: [query_orders]
---
这里是技能的系统提示词正文，告诉 LLM 如何执行这个技能。
可以写步骤、规则、示例等。
```

### 完整示例

见项目内置演示：`docs/demo-skills/capacity-report.md`

---

## Frontmatter 字段说明

所有字段都在 YAML frontmatter 中定义（用 `---` 包裹）：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `name` | string | ✅ | - | 技能唯一标识符，`^[a-z][a-z0-9-]{1,31}$` |
| `display_name` | string | ❌ | `name` | 显示名称，≤32 字符 |
| `description` | string | ✅ | - | 1~200 字符，用于自动匹配与菜单展示 |
| `when_to_use` | string[] | ❌ | `[]` | 触发短语，≤10 条，每条 ≤100 字符 |
| `allowed_tools` | string[] | ❌ | 只读工具集 | 允许使用的工具名列表 |
| `user_invocable` | bool | ❌ | `true` | 是否允许前端强制指定执行（`false` 时仅可被自动路由调用，SkillEngine 按触发来源强制校验） |
| `disable_model_invocation` | bool | ❌ | `false` | 是否禁用自动路由（仅允许用户显式选择） |
| `tool_preconditions` | dict | ❌ | `{}` | 工具前置断言，格式见下 |
| `version` | string | ❌ | `null` | 版本号，≤16 字符 |
| `author` | string | ❌ | `null` | 作者名，≤32 字符 |

### `tool_preconditions` 格式

给特定工具追加前置断言（断言实现在平台代码中，技能仅指定名称）：

```yaml
tool_preconditions:
  dispatch_work_order: ["dispatch_ready"]
  expedite_order: ["expedite_valid"]
```

含义：
- key: 工具名（必须在 `allowed_tools` 中）
- value: 断言名列表（必须是平台已注册的命名断言）

**安全不变式**：技能只能追加断言，不能移除或绕过平台内置的护栏与 ActionGate。

---

## 正文（系统提示词）

Frontmatter 之后的内容作为技能的系统提示词，发送给 LLM。正文有以下限制：

- 不能为空
- UTF-8 编码后 ≤ 32KB
- 支持 Markdown 格式（LLM 能理解）

**最佳实践**：
1. 明确角色定位
2. 给出清晰的步骤（如 1/2/3）
3. 说明如何使用工具
4. 强调不要臆造数据
5. 约定输出格式

### 正文预编译

平台会在技能正文前自动添加以下前缀：

```
你是技能执行体。严格按下方 SKILL.md 正文步骤推进，只用允许的工具查证/操作，
不要臆造数据；写操作被护栏拦截时如实说明原因。

---

[你的技能正文]
```

---

## Zip 包格式

技能可以打包为 `.zip` 以包含附属文件（参考数据、模板等）：

### 目录结构

```
my-skill.zip
└── SKILL.md          # 必须有
├── templates/
│   └── report.md
└── references/
    └── data.csv
```

或者带顶层目录（会自动归一化）：

```
my-skill.zip
└── my-skill/
    ├── SKILL.md
    └── ...
```

### 读取附属文件

技能可以通过 `read_skill_file` 工具读取自身的附属文件：

```python
# 工具签名
read_skill_file(skill_name: str, path: str) -> dict
# 返回: {"path": str, "bytes": bytes}
```

示例（在技能正文中使用）：

```markdown
...
2. 用 read_skill_file 读取参考模板 templates/report.md
3. 按模板格式输出报告
...
```

**注意**：只有当技能的 `file_count > 0` 时，`read_skill_file` 才会被自动加入 `allowed_tools`。

### Zip 包限制

- 总大小 ≤ 10MB（解压后）
- 成员数 ≤ 50（不含目录）
- 禁止符号链接
- 禁止路径穿越（`../`）

---

## 如何导入技能

### 前端导入

1. 点击输入框左侧的「技能」图标
2. 点击「导入技能」
3. 选择 `.md` 或 `.zip` 文件
4. 验证无误后确认导入

### HTTP API

```bash
# 导入
curl -X POST http://localhost:8000/api/v1/skills/import \
  -F "file=@my-skill.md"

# 列出已导入技能
curl http://localhost:8000/api/v1/skills

# 删除
curl -X DELETE http://localhost:8000/api/v1/skills/my-skill
```

详见 `docs/api-contract/api-contract-v2.md` §7。

---

## 可用工具

技能的 `allowed_tools` 只能从平台已注册的工具中选择。以下是内置工具：

### 只读工具（默认集）

| 工具名 | 说明 |
|--------|------|
| `query_orders` | 查询订单 |
| `query_work_orders` | 查询任务令 |
| `query_inventory` | 查询库存 |
| `check_kitting` | 检查齐套情况 |
| `read_skill_file` | 读取技能附属文件（自动追加） |

### 写工具（需显式声明）

| 工具名 | 说明 | 内置断言 |
|--------|------|----------|
| `dispatch_work_order` | 下发任务令 | `dispatch_ready` |
| `expedite_order` | 加急订单 | `expedite_valid` |

注：写工具仍受 ActionGate 约束，可能需要人工确认。

---

## 技能执行流程

```
用户消息
    │
    ▼
┌─────────────────────────────────┐
│ 路由层（三层）                  │
│ 1. embedding 语义匹配          │ ← 匹配 when_to_use
│ 2. LLM 分类                     │ ← 候选技能 + 描述
│ 3. 澄清（低置信）              │
└─────────────────────────────────┘
    │
    ▼ (intent="skill", skill_id="...")
┌─────────────────────────────────┐
│ SkillEngine                     │
│ 1. 加载 SKILL.md                │
│ 2. 装配 allowed_tools           │
│ 3. 装配 extra_preconditions      │
│ 4. 构造 AgentLoop               │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ ReAct 循环（受护栏约束）        │
│ 思考 → 工具调用 → 观察 → …     │
└─────────────────────────────────┘
    │
    ▼
最终回复
```

---

## 路由机制

### 自动匹配

当 `disable_model_invocation=false` 时，技能会参与自动路由：

1. **Embedding 层**：`when_to_use` 中的短语会被向量化，与用户消息做语义相似度匹配
2. **LLM 层**：所有可路由技能的 `name` + `description` 会被拼接到分类提示词中，供 LLM 选择

### 显式选择

用户可以在前端技能菜单中显式选择技能，此时会跳过路由层，走 `route_method="forced"` 分支。

---

## 护栏与安全

技能执行继承平台的全部安全机制：

| 机制 | 说明 |
|------|------|
| `allowed_tools` | 技能只能用声明过的工具 |
| 工具内置断言 | 写工具自带的前置检查（如 `dispatch_ready`） |
| 技能前置断言 | `tool_preconditions` 追加的额外检查 |
| ActionGate | 敏感操作需要人工确认（`/chat/confirm`） |
| 审计日志 | 所有工具调用、路由决策都会被记录 |

**安全不变式**：
- 技能不能调用未声明的工具
- 技能不能绕过内置断言
- 技能不能禁用 ActionGate
- 技能不能读取自身目录外的文件

---

## 示例技能

### 1. 产能日报（已内置）

见 `docs/demo-skills/capacity-report.md`

```markdown
---
name: capacity-report
display_name: 产能日报
description: 汇总当日订单/任务令/齐套数据，生成产能与瓶颈分析报告
when_to_use:
  - 给我出一份今天的产能报告
  - 分析一下最近的产线瓶颈
allowed_tools: [query_orders, query_work_orders, check_kitting]
user_invocable: true
disable_model_invocation: false
version: "1.0"
author: 周文涛
---
你是产能分析技能的执行体。按以下步骤推进：

1. 用 query_work_orders 拉取今日任务令，用 query_orders 取关联订单。
2. 用 check_kitting 核对各任务令齐套情况。
3. 汇总产能占用与瓶颈，给出结论与建议后续；不要臆造数据。
```

### 2. 带附属文件的技能

目录结构：
```
weekly-report.zip
├── SKILL.md
└── templates/
    └── summary.md
```

`SKILL.md`:
```markdown
---
name: weekly-report
display_name: 周报生成
description: 按模板生成周度生产报告
when_to_use:
  - 出一份周报
allowed_tools: [query_orders, query_work_orders]
---
1. 用 read_skill_file 读取 templates/summary.md 模板
2. 拉取本周数据
3. 按模板格式输出
```

---

## 错误码与排查

| HTTP | 场景 | 说明 |
|------|------|------|
| 413 | 文件太大 | 上传超过 10MB |
| 415 | 格式不对 | 仅支持 `.md` / `.zip` |
| 422 | 校验失败 | frontmatter 非法、正文空、工具/断言名不存在、zip 结构错误等 |
| 409 | 重名 | `name` 与已有技能冲突 |

导入时会返回具体错误信息。

---

## 与知识库的区别

| 维度 | 技能（Skills） | 知识库（Knowledge） |
|------|----------------|---------------------|
| 用途 | 封装流程与逻辑 | 存储参考文档 |
| 形式 | SKILL.md + 附件 | 纯文档 |
| 执行 | ReAct 循环 | RAG 检索增强 |
| 工具 | 可调用平台工具 | 只读 |
| 路由 | 可被自动匹配 | 总是可用 |

---

## 目录结构（已导入）

技能导入后存储在 `maestro/data/skills/`：

```
data/skills/
├── index.json           # 索引（自动维护）
├── capacity-report/
│   └── SKILL.md
└── weekly-report/
    ├── SKILL.md
    └── templates/
        └── summary.md
```

`index.json` 格式：
```json
[
  {
    "name": "capacity-report",
    "display_name": "产能日报",
    "description": "...",
    "when_to_use": ["..."],
    "allowed_tools": ["query_orders", "..."],
    "user_invocable": true,
    "disable_model_invocation": false,
    "tool_preconditions": {},
    "version": "1.0",
    "author": "周文涛",
    "file_count": 0,
    "bytes": 1024,
    "added_at": "2026-07-06T00:00:00Z"
  }
]
```

---

## 更多设计文档

- 原始设计：`docs/skills/skills-design-v1.md`
- 实现对齐：`docs/skills/skills-design-v2.md`
- 实现计划：`docs/skills/skills-implementation-plan.md`
- API 契约：`docs/api-contract/api-contract-v2.md` §7
