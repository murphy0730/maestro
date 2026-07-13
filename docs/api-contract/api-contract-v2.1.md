# API 契约 v2.1 增量（2026-07-14）

> 基于 `api-contract-v2.md` 的**增量修订**，只记录本轮缺陷修复（见
> `test-results/functional-test-20260713-191413/defects.md`）引入的契约变化，
> 其余条目以 v2 为准。v2 原文不改动。

## 1. `/models` 与 `/admin/reload-model`（DEF-5）

- `PUT /models`、`POST /admin/reload-model` 纳入 **Bearer 管理凭证** 保护
  （同 §7.1 管理端点），无凭证/凭证错误 → `401`，且不产生持久化变更与审计副作用。
- `GET /models` 响应**脱敏**：每个 provider 的 `api_key` 恒为 `""`，新增派生字段
  `api_key_set: bool` 标记是否已配置密钥。

```jsonc
// GET /models 响应增量
{ "llm": { "providers": [
    { "id": "p1", "name": "…", "base_url": "…", "model": "…",
      "api_key": "",            // 恒为空串，不再回传明文
      "api_key_set": true }     // v2.1 新增
  ], "active_id": "p1" }, "embedding": { /* 同构 */ } }
```

- **写语义**：`PUT /models` 载荷中某 provider `api_key == ""` 且 `id` 与已存条目
  匹配时，**保留已存密钥**（前端"回读-保存"不会清空 key）；显式非空 key 照常覆盖。
- 成功的 PUT / reload 产生审计条目 `models.update` / `models.reload`。

## 2. `StoredMessage` 增加附件元数据（DEF-4）

`GET /sessions/{id}/messages` 的消息对象新增可选字段；`content` 恒为**用户原文**，
不再包含 `<attachment>` 包装文本（包装文本仅作为当轮模型输入，不落库）：

```jsonc
// StoredMessage v2.1
{ "role": "user", "content": "分析附件", "ts": "ISO", "kind": "normal",
  "attachments": [ { "name": "orders.csv", "size": 7 } ] }   // v2.1 新增；只存元数据
```

旧数据无该字段 → 读出为 `[]`，向后兼容。

## 3. `run_skill_script` 结果增加 `fallback_reason`（DEF-3）

SRT 沙箱**运行期基础设施故障**（如数据根路径过长导致 mux socket EINVAL）时，
后端自动以宿主机受控模式重跑一次，结果对象：

```jsonc
{ "status": "completed", "execution_mode": "guarded_host",
  "fallback_reason": "srt_infrastructure_failure",   // v2.1 新增，仅回退时出现
  /* 其余字段同 v2 */ }
```

脚本自身失败不触发回退。另外执行现场目录移至系统临时目录（产物仍归档在
`<数据根>/executions/artifacts/<run_id>`，对外契约不变）。

## 4. `/scheduling/execute` 终态语义收紧（DEF-7）

对已处理（非 `pending` 状态）动作，无论 `confirmed` 取值一律 → `409`，
与 v2 §3「已处理过 → 409」的表述对齐（v2 实现仅在 `confirmed=true` 时 409）。

## 5. 待确认动作去重（DEF-6，行为说明）

同一 `action_type` + 相同结构化业务键（`wo_id`/`material_id`/`recipient` 等，
不含自由文本）已存在未过期 `pending` 动作时，新的挂起请求**复用既有动作**
（`actions` 帧返回既有 `action_id`），并产生 `dedup_hit` 审计。前端确认卡按
`action_id` 幂等，无需改动。

## 6. 其它行为修正（无契约形状变化）

- `GET /audit`、`GET /audit/timeline`：审计历史随进程启动自 `audit.jsonl` 尾部回灌
  （默认 2000 条），跨重启可查（DEF-1）；`session_id` 过滤在截断 `limit` 之前生效。
- 技能运行白名单始终包含只读工具 `read_observation`（DEF-2），大观察句柄的分页
  提示可被执行。
- agent 文件工具（`read_file`/`write_file`/`edit_file`/`list_files`）锚定
  `<数据根>/executions/workspace`，不再触碰源码树（DEF-9）。
