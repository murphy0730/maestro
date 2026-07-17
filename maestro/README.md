# Agent Runtime

这是一个统一的、策略治理的 Agent Runtime。每个请求都会创建一个持久化 Run；Runtime 根据
`RunIntent` 选择快速循环或受控执行。快速循环只能升级为受控执行，不能降级。

Runtime 不内置排产、齐套、催料、派工、RAG 或其他制造业务能力。业务能力必须通过受治理的
Skill、Tool 或 MCP 在运行时安装；所有副作用都先经过 Policy Gate，并在需要时创建审批记录。

## 安装与运行

```bash
cd maestro
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# HTTP API
uvicorn maestro.main:app --reload

# 交互式 CLI
python -m maestro.cli
```

可选地从 `.env.example` 复制 `.env` 并配置 `LLM_API_KEY`。未配置模型密钥时，Runtime 仍可
创建、恢复、取消和审计 Run；模型回答会进入受限的降级行为，测试不会访问网络。

## HTTP 契约

- `POST /runs`：创建并异步执行 Run。
- `GET /runs/{run_id}`、`GET /runs/{run_id}/stream`：读取 Run 与可恢复 SSE 流。
- `POST /runs/{run_id}/approvals/{approval_id}`：按 revision 审批或拒绝副作用。
- `POST /runs/{run_id}/cancel`：幂等取消 Run。
- `/sessions`：v3 会话元数据与消息历史。
- `/artifacts`：内容寻址的输入/输出工件。

详见 [统一 Runtime API](../docs/api-contract/agent-runtime-v1.md)。

## CLI

```text
run <目标>                         创建并执行 Run
resume <run_id>                    从持久化状态继续非终态 Run
approve <run_id> <approval_id> <revision> [yes|no]
cancel <run_id>                    取消 Run
skills                             列出已发现的 Claude 兼容 Skills
mcp                                列出当前注册的 MCP capabilities
help                               查看命令
```

Skill 使用 Claude Code 兼容目录：每个 Skill 以 `SKILL.md` 开头，先加载 metadata，只有匹配后
才加载完整说明；`references/`、`scripts/` 和资产只在明确请求时读取。Skill 的 `allowed-tools`
只能收窄权限，不能提高 Tool/MCP 的确定性风险等级。

## 验证

```bash
cd maestro && pytest
cd ../frontend && npm test && npm run build && npm run lint
```
