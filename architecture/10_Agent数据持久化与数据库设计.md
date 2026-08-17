# Agent 数据持久化与数据库设计

> 文档编号：10  
> 目标：为 Session、Event、Checkpoint、Plan、Tool、Skill、Evidence 和 Tool Result 提供可审计、可回放的数据持久化模型。  
> 数据库示例采用 PostgreSQL。

---

## 1. 数据分层

建议区分：

```text
Definition Data
Runtime State
Immutable Events
Derived Checkpoints
Large External Results
Observability Data
```

避免所有数据塞入一张 messages 表。

---

## 2. 核心实体

第一版推荐：

```text
agent_session
agent_event
session_checkpoint

plan
plan_task

tool_registry
skill_registry

tool_result

evidence_usage
```

可选：

```text
agent_trace_metric
```

---

## 3. agent_session

```sql
CREATE TABLE agent_session (
    session_id              VARCHAR(64) PRIMARY KEY,
    agent_id                VARCHAR(64) NOT NULL,
    agent_definition_version VARCHAR(64) NOT NULL,
    prefix_hash             VARCHAR(128) NOT NULL,
    model_id                VARCHAR(128) NOT NULL,

    status                  VARCHAR(32) NOT NULL DEFAULT 'active',

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

用途：

- 冻结 Agent Definition
- 绑定 Model
- 管理 Session 生命周期

---

## 4. agent_event

```sql
CREATE TABLE agent_event (
    event_id        VARCHAR(64) PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,
    sequence_no     BIGINT NOT NULL,
    event_type      VARCHAR(64) NOT NULL,

    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    references      JSONB NOT NULL DEFAULT '{}'::jsonb,

    token_count     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(session_id, sequence_no)
);

CREATE INDEX idx_agent_event_session_seq
ON agent_event(session_id, sequence_no);

CREATE INDEX idx_agent_event_type
ON agent_event(event_type);
```

第一版使用 JSONB 允许 Event 类型快速演进。

---

## 5. session_checkpoint

```sql
CREATE TABLE session_checkpoint (
    checkpoint_id       VARCHAR(64) PRIMARY KEY,
    session_id          VARCHAR(64) NOT NULL,

    parent_checkpoint_id VARCHAR(64),
    generation          INTEGER NOT NULL,

    covered_until_seq   BIGINT NOT NULL,

    state_json          JSONB NOT NULL,

    token_count         INTEGER,
    build_type          VARCHAR(32) NOT NULL,
    -- incremental / force / full_rebase

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_checkpoint_session_generation
ON session_checkpoint(session_id, generation DESC);
```

不直接覆盖旧 Checkpoint。

---

## 6. plan

```sql
CREATE TABLE plan (
    plan_id         VARCHAR(64) PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,
    goal            TEXT NOT NULL,
    status          VARCHAR(32) NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 7. plan_task

```sql
CREATE TABLE plan_task (
    task_id         VARCHAR(64) PRIMARY KEY,
    plan_id         VARCHAR(64) NOT NULL,

    parent_task_id  VARCHAR(64),
    title           TEXT NOT NULL,
    description     TEXT,

    status          VARCHAR(32) NOT NULL,
    priority        INTEGER,
    sequence_no     INTEGER,

    depends_on      JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);
```

完整 TODO 存在这里，不每轮放 Context。

---

## 8. tool_registry

Tool Registry 既可以在数据库，也可以由 MCP Provider 动态构建。

```sql
CREATE TABLE tool_registry (
    tool_id         VARCHAR(128) NOT NULL,
    version         VARCHAR(64) NOT NULL,

    name            VARCHAR(128) NOT NULL,
    description     TEXT NOT NULL,
    namespace       VARCHAR(128) NOT NULL,

    provider_type   VARCHAR(32) NOT NULL,
    provider_id     VARCHAR(128),

    input_schema    JSONB NOT NULL,

    aliases         JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,

    schema_hash     VARCHAR(128),
    is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY(tool_id, version)
);
```

Tool Search Index 可以基于此表同步到向量/全文索引。

---

## 9. skill_registry

```sql
CREATE TABLE skill_registry (
    skill_id        VARCHAR(128) NOT NULL,
    version         VARCHAR(64) NOT NULL,

    name            VARCHAR(128) NOT NULL,
    description     TEXT NOT NULL,

    body            TEXT NOT NULL,
    content_hash    VARCHAR(128),
    estimated_tokens INTEGER,

    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY(skill_id, version)
);
```

---

## 10. tool_result

大结果不放 agent_event.payload。

```sql
CREATE TABLE tool_result (
    result_id       VARCHAR(64) PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,
    tool_id         VARCHAR(128) NOT NULL,
    tool_version    VARCHAR(64),

    status          VARCHAR(32) NOT NULL,

    digest          JSONB,
    raw_payload     JSONB,
    external_ref    TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

大型数据可改为对象存储，只保留 `external_ref`。

---

## 11. evidence_usage

```sql
CREATE TABLE evidence_usage (
    usage_id        VARCHAR(64) PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,

    evidence_id     VARCHAR(128) NOT NULL,
    source_type     VARCHAR(32) NOT NULL,
    source_ref      TEXT NOT NULL,

    derived_fact    TEXT,
    usage_type      VARCHAR(32),

    event_id        VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

用于：

- Evidence Used Rate
- 决策审计
- RAG Eval

---

## 12. Source Ref 规范

推荐统一 URI 风格：

```text
event://evt_123
tool-result://R123
tool://wms/query_inventory/2.1
skill://production_scheduling/2.3
rag://DOC-123/C18
memory://MEM-18
plan://PLAN-1/T4
```

优点：

- 人可读
- 容易路由
- Checkpoint 不需要复制实体内容

---

## 13. Event Append-Only

不要：

```sql
UPDATE agent_event SET payload = ...
```

修改历史业务语义。

状态变更写新 Event。

Telemetry 字段若确需补充，可单独处理，但不要改变原始业务事实。

---

## 14. Checkpoint 与 Event 一致性

Checkpoint 保存：

```text
covered_until_seq
```

ContextBuilder：

```text
checkpoint = latest CP
hot_events =
    event.sequence_no > checkpoint.covered_until_seq
```

这是一条非常关键的装配边界。

---

## 15. Full Rebase

读取：

```sql
SELECT *
FROM agent_event
WHERE session_id = ?
ORDER BY sequence_no;
```

重新构建 Canonical Checkpoint。

因此必须保留原始 Event。

---

## 16. Tool Version 审计

TOOL_CALL Event 必须写：

```text
tool_id
tool_version
```

否则以后 Registry 已升级时无法知道当时调用的是哪个定义。

Skill 同理。

---

## 17. 数据保留策略

可以按层设计：

### 长期

- Session
- Event
- Checkpoint
- 关键 Tool Result
- Evidence Usage

### 可过期

- 非关键大 Raw Result
- Tool Search Debug Ranking
- 临时 retrieval cache

但涉及生产决策审计的数据应根据企业合规要求单独制定保留周期。

---

## 18. 事务与幂等

Tool 副作用操作必须考虑：

```text
idempotency_key
```

例如：

```text
publish_schedule(session_id + schedule_version)
```

防止 Agent 重试造成重复下发。

建议在 Tool Call Event 中记录：

```yaml
idempotency_key:
```

---

## 19. 并发

若一个 Session 只允许一个主 Agent Loop：

- 使用 session lock
- 或 optimistic version

防止两个并发轮次产生相同 sequence。

若未来支持并行 SubAgent，则：

- Event 仍有全局 Session sequence
- metadata 保存 branch / worker id

---

## 20. 第一版边界

先使用 PostgreSQL + JSONB 足够。

不要第一版同时引入：

- EventStore 专用数据库
- 图数据库
- 多套向量数据库
- 复杂 CQRS

当 Event 量和查询模式稳定后再优化。
