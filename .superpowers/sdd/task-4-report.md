# Task 4 报告：Claude 兼容 Skill 发现与渐进加载

## 需求映射

| 简报要求 | 实现与证据 |
| --- | --- |
| 兼容 fixtures | 新增 inline、fork、resources fixture；resources 的 guide 与 script 独立存放。 |
| 严格 Runtime 契约且不破坏旧路径 | `RuntimeSkillFrontmatter` 与旧 `SkillFrontmatter` 分离；未知前言写入 `extensions`，旧 `tool_preconditions` / `scripts` 仍只属于 legacy SkillEngine。 |
| 渐进加载 | `SkillCatalog.discover()` 只读取最多 16KB 的前言；`load()` 才读完整 SKILL.md；`read_resource()` 才读资源。大正文测试确保发现不误读正文。 |
| 前言字段与替换 | 解析 Claude 连字符字段及 context/agent/model/effort/hooks/shell；load 替换 `$ARGUMENTS`、`${CLAUDE_SKILL_DIR}`、`${CLAUDE_SESSION_ID}`。 |
| 来源优先级 | 采用 `managed > user > project > additional > plugin > bundled > mcp`；低优先级同名项保留在 `inactive` 供诊断。 |
| 工具与远端安全 | Claude 工具别名映射到 CapabilityRegistry snapshot；未知工具失败；MCP 来源携带 inline shell 时抛出 `RemoteSkillExecutionDenied`；资源路径拒绝绝对路径、反斜杠、控制字符、`..` 与逃逸 symlink。 |
| Runtime Core 业务隔离 | 新模块只依赖 capability snapshot 和 skill parser；未添加制造业务能力。 |

## TDD 证据

1. 初始新增兼容测试后执行 `cd maestro && pytest tests/runtime/test_skills_compat.py -v`：收集阶段因 `ModuleNotFoundError: No module named 'maestro.runtime.skills'` 失败（RED）。
2. 实现最小 catalog/schema/parser 后，同命令：7 passed（GREEN）。
3. 新增大正文 discovery 回归测试后执行单测：因 `runtime skill frontmatter exceeds 16KB` 失败（RED）。
4. 将 discovery 调整为在 16KB 内寻找结束分隔符、只保留前言后，执行 `pytest tests/runtime/test_skills_compat.py -v`：8 passed（GREEN）。
5. 复审补充的 RED：新增未 discover 资源读取、大正文上限、跨平台绝对路径与 Unicode Cc 测试后，兼容测试 15 项中 5 项失败，分别证明了全量 `read_text()`、第 16KB+1 字节读取、`C:/...`/DEL/U+0085 未在校验阶段拒绝。
6. 复审 GREEN：资源读取的未 discover 查找改用同一个有界 metadata 读取路径；读取循环从 `< 16KB` 截止；资源名新增 drive/UNC 与 Unicode Cc 检查。`pytest tests/runtime/test_skills_compat.py -v`：15 passed。

## 验证

- `cd maestro && pytest tests/runtime/test_skills_compat.py tests/test_skills.py -v`：50 passed。
- `cd maestro && pytest`：359 passed、7 failed。所有失败都是既有 `tests/test_chroma_store.py` 的 `ModuleNotFoundError: chromadb`；Task 4 runtime/legacy Skill 测试均通过。
- `git diff --check`：无输出。
- 复审后：`cd maestro && pytest tests/runtime/test_skills_compat.py tests/test_skills.py -v`：57 passed。
- 复审后：`cd maestro && pytest`：366 passed、7 failed；失败仍全部为 `tests/test_chroma_store.py` 的 `ModuleNotFoundError: chromadb`。

## 提交

- `2be033d feat: load Claude-compatible skills progressively`（随后仅更新本报告的提交 hash 并 amend）。

## 顾虑

- 当前测试解释器 `/opt/miniconda3/bin/python3.13` 未安装 `chromadb`。已安装 `python-pptx`，其原有 office tests 已恢复通过；两次安装 chromadb 的 21.7MB wheel 下载在本环境被中断，故无法让完整套件达到全绿。代码未修改 Chroma 或 office 功能。
