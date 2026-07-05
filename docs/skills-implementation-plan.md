# Skill/Command 技能模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为排产调度 Agent 新增可插拔技能模块(SKILL.md = frontmatter + prompt),支持 zip/md 上传、用户显式选择 + 意图路由第四类 "skill" 自动匹配、复用 AgentLoop 执行并继承全部护栏,含技能级前置断言。

**Architecture:** 新建后端 `skills/` 包(schemas/parser/store/engine,与三引擎平级),复用 `AgentLoop`(ReAct)执行技能正文;意图路由扩展第四类 "skill"(embedding 吃 `when_to_use` 向量 + LLM 分类吃候选列表 + forced 显式分支);前端 Composer 加「技能」chip + Popover + 导入弹窗。规范源 `docs/skills-design-v1.md`,实现定稿 `docs/skills-design-v2.md`(三分叉 A1/B1/C1 + 15 条 drift 对齐 + 前置断言落地)。

**Tech Stack:** Python 3.12 / FastAPI / pydantic v2 / pyyaml / stdlib zipfile / pytest;React 18 / Vite / TS / Tailwind / TanStack Query / Zustand / vitest + RTL / MSW。

## Global Constraints

- 后端包名 **`scheduling_platform`**(非 `platform`,会 shadow stdlib)。
- frontmatter 手写解析(`---` split + `yaml.safe_load`,pyyaml 已有);zip 用 stdlib `zipfile`;**零新增依赖**。
- 正文 ≤32KB;zip 成员 ≤50;解压总大小 ≤10MB(对齐 `main.py:435` 的 `_MAX_UPLOAD_BYTES`)。
- `name` 校验 `^[a-z][a-z0-9-]{1,31}$`,全局唯一(即 skill_id / 目录名 / URL 段)。
- 默认 `allowed_tools = QUERY_READONLY_TOOLS`(`foundation/tools/builtin.py:358`,含 `query_orders`/`query_inventory`/`query_work_orders`/`check_kitting`)。
- 安全不变量:**前置断言只叠加不替换**——内置断言、ActionGate 不受技能影响;技能包只声明断言名,断言实现永远是平台代码。
- HTTP 错误:422(`SkillValidationError`)/ 409(name 重复)/ 413(>10MB)/ 415(后缀非 .zip/.md);`POST /skills/import` 返回 **201**(drift #8)。
- 前端 token:Modal 用 `bg-surface-1`(drift #1,`bg-surface-raised` 不存在);`ROUTE_META.skill.fg = text-accent-fg` + `leftBorder: border-l-accent`(drift #2)。
- 设计文档修订另存新版本(用户偏好):v1/v2 已在 `docs/`;本计划单独存放。
- 提交信息末尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## File Structure

### 后端新建(`scheduling_platform/src/scheduling_platform/skills/`)
- `__init__.py` — 包导出。
- `schemas.py` — `SkillValidationError`、`SkillFrontmatter`(pydantic + field_validator)、`SkillMeta`(加 file_count/bytes/added_at)。纯数据,不依赖运行时(foundation/tools)。
- `parser.py` — `parse_skill_md`、`extract_package`、`validate_allowed_tools`。
- `store.py` — `SkillStore`(catalog + 落盘 + version + 路由数据供给)。
- `engine.py` — `SkillEngine`(组装 AgentLoop 执行)。

### 后端修改
- `engines/scheduling/agent_loop.py` — `__init__` 加 `extra_preconditions` 参数;`_handle_call` 插入追加断言块。
- `orchestrator/schemas.py` — `RouteDecision.intent` 加 `"skill"`、加 `skill_id: str | None`。
- `orchestrator/embedding_router.py` — 构造加 `skills` 引用;version 拉式失效;`_ensure_skill_vectors`。
- `orchestrator/router.py` — `CLASSIFY_SYSTEM` → `_classify_system(skill_candidates)`;`IntentRouter` 加 `skills`;classify 后校验 skill_id。
- `orchestrator/orchestrator.py` — 构造加 `skill_engine`;`handle` 加 `skill_id`;forced 分支;`_gate_and_dispatch`/`_dispatch`/`_record_route` 加 skill。
- `bootstrap.py` — 构造 SkillStore + `read_skill_file` 工具 + `named_preconditions` + SkillEngine;wire EmbeddingRouter/IntentRouter/Orchestrator;`Platform` 加 `skill_store`/`skill_engine`/`named_preconditions` 字段。
- `config.py` — `Settings` 加 `skills_dir`。
- `main.py` — 三端点;`ChatRequest`/`ChatStreamRequest` 加 `skill_id`;`_contract_route` 加 `skill_id`;`/chat`/`/chat/stream` 透传。
- `tests/test_skills.py`、`tests/test_skill_routing.py` — 新建测试。

### 前端新建(`frontend/src/`)
- `api/skills.ts` — `listSkills`/`importSkill`/`deleteSkill`。
- `components/ui/Modal.tsx` — 最小居中弹窗原语。
- `features/orchestrator/skills/SkillMenu.tsx` — chip + Popover。
- `features/orchestrator/skills/SkillImportModal.tsx` — 导入弹窗。
- `features/orchestrator/skills/SkillMenu.test.tsx`、`SkillImportModal.test.tsx`。
- `api/skills.test.ts` — hook 测试(可选,照 `useStreamingChat.test.tsx`)。

### 前端修改
- `types/api.ts` — `SkillMeta`/`SkillListResponse`;`IntentType` 加 `'skill'`;`RouteDecision` 加 `skill_id?`;`ChatStreamRequest` 加 `skill_id?`。
- `types/index.ts` — `RouteEngine` 加 `'skill'`。
- `lib/routes.ts` — `ROUTE_META` 加 `skill` 条目。
- `api/queryKeys.ts` — 加 `skills.list()`。
- `api/hooks.ts` — `useSkills`/`useImportSkill`/`useDeleteSkill`。
- `api/index.ts` — re-export。
- `mocks/api/fixtures.ts` — `SKILLS` 夹具。
- `mocks/api/handlers.ts` — GET/POST/DELETE /skills。
- `features/orchestrator/Composer.tsx` — `OpenMenu` 加 `'skill'`;插 `<SkillMenu/>`;props 透传。
- `pages/Workspace.tsx` — `useState<SkillMeta|null>`;互斥;`onSend` 透传 `skillId`。
- `hooks/useOrchestrator.ts` — `send` 加 `skillId`。
- `hooks/useStreamingChat.ts` — `send` 加 `skillId`;请求体加 `skill_id`。
- `features/query/knowledge/UploadProgress.tsx` — 加 `fillClassName` prop。

---

## Phase 1: 解析与存储

### Task 1.1: `skills/schemas.py` — frontmatter 数据模型

**Files:**
- Create: `scheduling_platform/src/scheduling_platform/skills/__init__.py`
- Create: `scheduling_platform/src/scheduling_platform/skills/schemas.py`
- Test: `scheduling_platform/tests/test_skills.py`

**Interfaces:**
- Produces: `SkillValidationError(Exception)`、`SkillFrontmatter(BaseModel)`(字段见 v1 §2.2)、`SkillMeta(SkillFrontmatter)`(加 `file_count:int`、`bytes:int`、`added_at:str`)。

- [ ] **Step 1: Write the failing test** (`tests/test_skills.py`)

```python
import pytest
from datetime import datetime, timezone
from scheduling_platform.skills.schemas import SkillFrontmatter, SkillMeta, SkillValidationError


def _base(**kw):
    return {"name": "capacity-report", "description": "产能日报", **kw}


def test_frontmatter_ok_minimal():
    fm = SkillFrontmatter(**_base())
    assert fm.name == "capacity-report"
    assert fm.user_invocable is True
    assert fm.disable_model_invocation is False
    assert fm.tool_preconditions == {}
    assert fm.allowed_tools is None  # None 哨兵 = 校验时填默认
    assert fm.effective_display_name == "capacity-report"


def test_frontmatter_name_regex():
    for bad in ["X", "1a", "has_underscore", "a" * 33, "CAP"]:
        with pytest.raises(Exception):
            SkillFrontmatter(**_base(name=bad))


def test_frontmatter_description_length():
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(description=""))
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(description="x" * 201))


def test_frontmatter_when_to_use_limits():
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(when_to_use=["x" * 101]))
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(when_to_use=[str(i) for i in range(11)]))


def test_frontmatter_preconditions_types():
    fm = SkillFrontmatter(**_base(
        allowed_tools=["dispatch_work_order"],
        tool_preconditions={"dispatch_work_order": ["dispatch_ready"]},
    ))
    assert fm.tool_preconditions == {"dispatch_work_order": ["dispatch_ready"]}


def test_skillmeta_extra_fields():
    fm = SkillMeta(**_base(), file_count=2, bytes=1024, added_at="2026-07-05T00:00:00Z")
    assert fm.file_count == 2 and fm.bytes == 1024
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v`
Expected: FAIL with `ModuleNotFoundError: scheduling_platform.skills.schemas`

- [ ] **Step 3: Write minimal implementation** (`skills/__init__.py` 空,`skills/schemas.py`)

```python
# skills/__init__.py
from scheduling_platform.skills.schemas import SkillFrontmatter, SkillMeta, SkillValidationError

__all__ = ["SkillFrontmatter", "SkillMeta", "SkillValidationError"]
```

```python
# skills/schemas.py
from __future__ import annotations
import re
from pydantic import BaseModel, field_validator, model_validator, ValidationError

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


class SkillValidationError(Exception):
    """技能包校验失败 → HTTP 422。"""


class SkillFrontmatter(BaseModel):
    name: str
    display_name: str | None = None
    description: str
    when_to_use: list[str] = []
    allowed_tools: list[str] | None = None  # None 哨兵:校验时填 QUERY_READONLY_TOOLS
    user_invocable: bool = True
    disable_model_invocation: bool = False
    tool_preconditions: dict[str, list[str]] = {}
    version: str | None = None
    author: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("name 必须匹配 ^[a-z][a-z0-9-]{1,31}$")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        if not (1 <= len(v) <= 200):
            raise ValueError("description 长度需 1~200 字符")
        return v

    @field_validator("display_name")
    @classmethod
    def _display(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 32:
            raise ValueError("display_name 需 ≤32 字符")
        return v

    @field_validator("when_to_use")
    @classmethod
    def _when(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError("when_to_use 需 ≤10 条")
        for s in v:
            if len(s) > 100:
                raise ValueError("when_to_use 每条需 ≤100 字符")
        return v

    @field_validator("version")
    @classmethod
    def _ver(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 16:
            raise ValueError("version 需 ≤16 字符")
        return v

    @field_validator("author")
    @classmethod
    def _author(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 32:
            raise ValueError("author 需 ≤32 字符")
        return v

    @model_validator(mode="after")
    def _precond_types(self):
        for tool, names in self.tool_preconditions.items():
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                raise ValueError(f"tool_preconditions['{tool}'] 必须为 list[str]")
        return self

    @property
    def effective_display_name(self) -> str:
        return self.display_name or self.name


class SkillMeta(SkillFrontmatter):
    file_count: int = 0
    bytes: int = 0
    added_at: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/skills/__init__.py scheduling_platform/src/scheduling_platform/skills/schemas.py scheduling_platform/tests/test_skills.py
git commit -m "feat(skills): frontmatter 数据模型 (SkillFrontmatter/SkillMeta/SkillValidationError)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 1.2: `skills/parser.py` — frontmatter 解析 + zip 解包 + 工具/断言名校验

**Files:**
- Create: `scheduling_platform/src/scheduling_platform/skills/parser.py`
- Test: `scheduling_platform/tests/test_skills.py`(追加)

**Interfaces:**
- Consumes: `SkillFrontmatter`、`SkillValidationError`(Task 1.1)。
- Produces:
  - `parse_skill_md(text: str) -> tuple[SkillFrontmatter, str]`
  - `extract_package(data: bytes, filename: str) -> tuple[SkillFrontmatter, str, dict[str, bytes]]`
  - `validate_allowed_tools(fm, registered: set[str], default: list[str], named: set[str]) -> list[str]` — 返回解析后的 allowed_tools(`None` → default),并校验 `tool_preconditions` 的 key ⊆ allowed_tools、断言名 ⊆ named;失败抛 `SkillValidationError`。

- [ ] **Step 1: Write the failing tests** (追加到 `tests/test_skills.py`)

```python
import io, zipfile
from scheduling_platform.skills.parser import (
    parse_skill_md, extract_package, validate_allowed_tools,
)
from scheduling_platform.skills.schemas import SkillValidationError


def _md(fm: str, body: str = "正文") -> str:
    return f"---\n{fm}\n---\n{body}"


def test_parse_skill_md_ok():
    text = _md("name: cap\ndescription: 产能\nwhen_to_use:\n  - 出报告\n")
    fm, body = parse_skill_md(text)
    assert fm.name == "cap" and fm.description == "产能"
    assert body == "正文"


def test_parse_skill_md_no_frontmatter():
    with pytest.raises(SkillValidationError):
        parse_skill_md("no frontmatter here")


def test_parse_skill_md_empty_body():
    with pytest.raises(SkillValidationError):
        parse_skill_md("---\nname: cap\ndescription: x\n---\n   \n")


def test_parse_skill_md_body_too_large():
    text = _md("name: cap\ndescription: x\n", "x" * (32 * 1024 + 1))
    with pytest.raises(SkillValidationError):
        parse_skill_md(text)


def _zip(files: dict[str, bytes]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        for n, c in files.items():
            zf.writestr(n, c)
    return bio.getvalue()


def test_extract_package_md():
    data = _md("name: cap\ndescription: x\n", "正文").encode()
    fm, body, att = extract_package(data, "cap.md")
    assert fm.name == "cap" and body == "正文" and att == {}


def test_extract_package_zip_ok():
    z = _zip({"SKILL.md": _md("name: cap\ndescription: x\n", "正文"),
              "docs/ref.md": b"# ref"})
    fm, body, att = extract_package(z, "cap.zip")
    assert fm.name == "cap" and att == {"docs/ref.md": b"# ref"}


def test_extract_package_zip_top_dir_normalized():
    z = _zip({"pkg/SKILL.md": _md("name: cap\ndescription: x\n", "正文"),
              "pkg/docs/ref.md": b"# ref"})
    fm, body, att = extract_package(z, "cap.zip")
    assert att == {"docs/ref.md": b"# ref"}


def test_extract_package_zip_missing_skill_md():
    z = _zip({"docs/ref.md": b"# ref"})
    with pytest.raises(SkillValidationError):
        extract_package(z, "cap.zip")


def test_extract_package_zip_traversal():
    z = _zip({"../evil.md": b"x"})
    with pytest.raises(SkillValidationError):
        extract_package(z, "cap.zip")


def test_extract_package_zip_too_many_members():
    z = _zip({f"f{i}.md": b"x" for i in range(51)})
    # SKILL.md still required; if 51 members with no SKILL.md → 422 either way
    with pytest.raises(SkillValidationError):
        extract_package(z, "cap.zip")


def test_extract_package_bad_suffix():
    with pytest.raises(SkillValidationError):
        extract_package(b"x", "cap.txt")


def test_validate_allowed_tools_default():
    fm = SkillFrontmatter(name="cap", description="x")  # allowed_tools None
    out = validate_allowed_tools(fm, registered={"query_orders", "query_work_orders"},
                                 default=["query_orders"], named={"dispatch_ready"})
    assert out == ["query_orders"]


def test_validate_allowed_tools_unknown():
    fm = SkillFrontmatter(name="cap", description="x", allowed_tools=["nope"])
    with pytest.raises(SkillValidationError):
        validate_allowed_tools(fm, registered={"query_orders"}, default=[], named=set())


def test_validate_allowed_tools_precond_key_outside():
    fm = SkillFrontmatter(name="cap", description="x",
                          allowed_tools=["query_orders"],
                          tool_preconditions={"dispatch_work_order": ["dispatch_ready"]})
    with pytest.raises(SkillValidationError):
        validate_allowed_tools(fm, registered={"query_orders"}, default=[], named={"dispatch_ready"})


def test_validate_allowed_tools_precond_unknown_assertion():
    fm = SkillFrontmatter(name="cap", description="x",
                          allowed_tools=["dispatch_work_order"],
                          tool_preconditions={"dispatch_work_order": ["mystery"]})
    with pytest.raises(SkillValidationError):
        validate_allowed_tools(fm, registered={"dispatch_work_order"},
                               default=[], named={"dispatch_ready"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v`
Expected: FAIL with `ImportError: ...parser`

- [ ] **Step 3: Write minimal implementation** (`skills/parser.py`)

```python
from __future__ import annotations
import io
import zipfile
from pathlib import Path
import yaml
from pydantic import ValidationError
from scheduling_platform.skills.schemas import SkillFrontmatter, SkillValidationError

_BODY_MAX = 32 * 1024
_ZIP_MAX_MEMBERS = 50
_ZIP_MAX_TOTAL = 10 * 1024 * 1024


def parse_skill_md(text: str) -> tuple[SkillFrontmatter, str]:
    if not text.startswith("---"):
        raise SkillValidationError("frontmatter 必须以 '---' 开头")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillValidationError("frontmatter 缺少结束 '---'")
    fm_raw, body = parts[1], parts[2].lstrip("\n")
    try:
        data = yaml.safe_load(fm_raw)
    except yaml.YAMLError as e:
        raise SkillValidationError(f"frontmatter YAML 解析失败: {e}") from e
    if not isinstance(data, dict):
        raise SkillValidationError("frontmatter 必须解析为 dict")
    try:
        fm = SkillFrontmatter(**data)
    except ValidationError as e:
        raise SkillValidationError(str(e)) from e
    if not body.strip():
        raise SkillValidationError("正文不能为空")
    if len(body.encode("utf-8")) > _BODY_MAX:
        raise SkillValidationError("正文需 ≤32KB")
    return fm, body


def extract_package(data: bytes, filename: str) -> tuple[SkillFrontmatter, str, dict[str, bytes]]:
    name = filename.lower()
    if name.endswith(".md"):
        fm, body = parse_skill_md(data.decode("utf-8"))
        return fm, body, {}
    if name.endswith(".zip"):
        return _extract_zip(data)
    raise SkillValidationError("仅支持 .md / .zip 后缀")


def _extract_zip(data: bytes) -> tuple[SkillFrontmatter, str, dict[str, bytes]]:
    bio = io.BytesIO(data)
    try:
        zf = zipfile.ZipFile(bio)
    except zipfile.BadZipFile as e:
        raise SkillValidationError(f"zip 解压失败: {e}") from e
    members = [i for i in zf.infolist() if not i.is_dir()]
    if len(members) > _ZIP_MAX_MEMBERS:
        raise SkillValidationError(f"zip 成员数 >{_ZIP_MAX_MEMBERS}")
    files: dict[str, bytes] = {}
    total = 0
    for info in members:
        n = info.filename
        if n.startswith("/") or ".." in Path(n).parts:
            raise SkillValidationError(f"zip 含不安全路径: {n}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise SkillValidationError(f"zip 含符号链接: {n}")
        content = zf.read(n)
        total += len(content)
        if total > _ZIP_MAX_TOTAL:
            raise SkillValidationError("zip 解压后 >10MB")
        files[n] = content
    skill_path = _find_skill_md(files)
    if skill_path is None:
        raise SkillValidationError("zip 缺少 SKILL.md")
    prefix = str(Path(skill_path).parent)
    attachments: dict[str, bytes] = {}
    for path, content in files.items():
        rel = path[len(prefix) + 1:] if prefix != "." and path.startswith(prefix + "/") else path
        if rel == "SKILL.md" or path == skill_path:
            continue
        attachments[rel] = content
    fm, body = parse_skill_md(files[skill_path].decode("utf-8"))
    return fm, body, attachments


def _find_skill_md(files: dict[str, bytes]) -> str | None:
    if "SKILL.md" in files:
        return "SKILL.md"
    # 唯一顶层目录内
    top_dirs = {str(Path(p).parent) for p in files}
    if len(top_dirs) == 1:
        only = next(iter(top_dirs))
        candidate = f"{only}/SKILL.md"
        if candidate in files:
            return candidate
    return None


def validate_allowed_tools(
    fm: SkillFrontmatter,
    registered: set[str],
    default: list[str],
    named: set[str],
) -> list[str]:
    allowed = fm.allowed_tools if fm.allowed_tools is not None else list(default)
    unknown = [t for t in allowed if t not in registered]
    if unknown:
        raise SkillValidationError(f"allowed_tools 含未注册工具: {unknown}")
    bad = []
    for tool, names in fm.tool_preconditions.items():
        if tool not in allowed:
            bad.append(f"tool_preconditions key '{tool}' 不在 allowed_tools 内")
        for n in names:
            if n not in named:
                bad.append(f"tool_preconditions['{tool}'] 断言名 '{n}' 未注册")
    if bad:
        raise SkillValidationError("; ".join(bad))
    return allowed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v`
Expected: PASS (all parser + schema tests)

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/skills/parser.py scheduling_platform/tests/test_skills.py
git commit -m "feat(skills): frontmatter 解析 + zip 解包 + 工具/断言名校验

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 1.3: `skills/store.py` — SkillStore(catalog + 落盘 + version)

**Files:**
- Create: `scheduling_platform/src/scheduling_platform/skills/store.py`
- Test: `scheduling_platform/tests/test_skills.py`(追加)

**Interfaces:**
- Consumes: `SkillMeta`、`SkillFrontmatter`(Task 1.1)。
- Produces: `SkillStore`:
  - `__init__(self, base_dir: Path)`
  - `version: int`(save/delete 自增)
  - `list_all() -> list[SkillMeta]`、`get(name) -> SkillMeta | None`、`get_body(name) -> str`
  - `save(meta: SkillMeta, body: str, attachments: dict[str, bytes])`(重名 `KeyError`)
  - `delete(name) -> bool`
  - `read_attachment(name, rel_path, max_bytes=65536) -> dict`(防穿越)
  - `routable() -> list[SkillMeta]`、`routing_examples() -> dict[str, list[str]]`

- [ ] **Step 1: Write the failing tests** (追加)

```python
from pathlib import Path
from scheduling_platform.skills.store import SkillStore
from scheduling_platform.skills.schemas import SkillMeta


def _meta(name="cap", **kw):
    return SkillMeta(name=name, description="x", added_at="2026-07-05T00:00:00Z",
                     file_count=0, bytes=0, **kw)


def test_store_save_get_list(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    assert s.get("cap").name == "cap"
    assert s.get_body("cap") == "正文"
    assert [m.name for m in s.list_all()] == ["cap"]
    assert s.version == 1


def test_store_save_duplicate(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    with pytest.raises(KeyError):
        s.save(_meta("cap"), "正文2", {})


def test_store_persist_reload(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {"docs/r.md": b"# r"})
    s2 = SkillStore(tmp_path)  # 重启重载
    assert s2.get("cap").file_count == 1
    assert s2.get_body("cap") == "正文"
    assert s2.read_attachment("cap", "docs/r.md") == {"path": "docs/r.md", "bytes": b"# r"}


def test_store_delete(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    assert s.delete("cap") is True
    assert s.get("cap") is None
    assert s.delete("cap") is False
    assert s.version == 2


def test_store_read_attachment_traversal(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    with pytest.raises(SkillValidationError):
        s.read_attachment("cap", "../../etc/passwd")


def test_store_routable_and_examples(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("a", disable_model_invocation=False, when_to_use=["出报告"]), "b", {})
    s.save(_meta("b", disable_model_invocation=True, when_to_use=["x"]), "b", {})
    routable = [m.name for m in s.routable()]
    assert routable == ["a"]
    assert s.routing_examples() == {"skill:a": ["出报告"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v`
Expected: FAIL with `ImportError: ...store`

- [ ] **Step 3: Write minimal implementation** (`skills/store.py`)

```python
from __future__ import annotations
import json
import shutil
import threading
from pathlib import Path
from scheduling_platform.skills.schemas import SkillMeta, SkillValidationError


class SkillStore:
    def __init__(self, base_dir: Path):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._index_path = self._base / "index.json"
        self._lock = threading.Lock()
        self._index: list[SkillMeta] = []
        self.version = 0
        self._load_index()

    def _load_index(self) -> None:
        if self._index_path.exists():
            data = json.loads(self._index_path.read_text("utf-8"))
            self._index = [SkillMeta(**m) for m in data]

    def _save_index(self) -> None:
        self._index_path.write_text(
            json.dumps([m.model_dump() for m in self._index], ensure_ascii=False, indent=2),
            "utf-8",
        )
        self.version += 1

    def list_all(self) -> list[SkillMeta]:
        with self._lock:
            return sorted(self._index, key=lambda m: m.added_at, reverse=True)

    def get(self, name: str) -> SkillMeta | None:
        with self._lock:
            return next((m for m in self._index if m.name == name), None)

    def _skill_dir(self, name: str) -> Path:
        return self._base / name

    def get_body(self, name: str) -> str:
        return (self._skill_dir(name) / "SKILL.md").read_text("utf-8")

    def save(self, meta: SkillMeta, body: str, attachments: dict[str, bytes]) -> None:
        with self._lock:
            if any(m.name == meta.name for m in self._index):
                raise KeyError(meta.name)
            d = self._skill_dir(meta.name)
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(body, "utf-8")
            for rel, content in attachments.items():
                target = d / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self._index.append(meta)
            self._save_index()

    def delete(self, name: str) -> bool:
        with self._lock:
            before = len(self._index)
            self._index = [m for m in self._index if m.name != name]
            if len(self._index) == before:
                return False
            d = self._skill_dir(name)
            if d.exists():
                shutil.rmtree(d)
            self._save_index()
            return True

    def read_attachment(self, name: str, rel_path: str, max_bytes: int = 65536) -> dict:
        d = self._skill_dir(name)
        target = (d / rel_path).resolve()
        if not str(target).startswith(str(d.resolve())):
            raise SkillValidationError(f"路径越界: {rel_path}")
        if not target.is_file():
            raise SkillValidationError(f"附属文件不存在: {rel_path}")
        content = target.read_bytes()[:max_bytes]
        return {"path": rel_path, "bytes": content}

    def routable(self) -> list[SkillMeta]:
        with self._lock:
            return [m for m in self._index if not m.disable_model_invocation]

    def routing_examples(self) -> dict[str, list[str]]:
        with self._lock:
            return {f"skill:{m.name}": list(m.when_to_use)
                    for m in self._index if not m.disable_model_invocation and m.when_to_use}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v`
Expected: PASS (all Phase 1 tests)

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/skills/store.py scheduling_platform/tests/test_skills.py
git commit -m "feat(skills): SkillStore 持久化 + catalog + version + 路由数据供给

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Phase 2: HTTP + bootstrap 装配

### Task 2.1: `config.skills_dir` + bootstrap 装配 SkillStore / `read_skill_file` / `named_preconditions`

**Files:**
- Modify: `scheduling_platform/src/scheduling_platform/config.py`(加 `skills_dir`,照 `sessions_dir` 范式 `config.py:50-63`)
- Modify: `scheduling_platform/src/scheduling_platform/bootstrap.py`(构造 store / 注册工具 / 构造 named_preconditions / `Platform` 加字段)
- Test: `scheduling_platform/tests/test_skills.py`(追加 bootstrap 烟测)

**Interfaces:**
- Produces: `Platform.skill_store: SkillStore`、`Platform.named_preconditions: dict[str, Precondition]`;注册工具 `read_skill_file(skill_name: str, path: str) -> dict`(kind="read")。

- [ ] **Step 1: Write the failing test** (追加;照 `test_router.py` 的 `build_platform` 范式)

```python
from scheduling_platform.bootstrap import build_platform
from scheduling_platform.config import Settings


def test_bootstrap_wires_skill_store_and_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(llm_api_key="", audit_log_file=None,
                 sessions_dir=tmp_path / "sessions", skills_dir=tmp_path / "skills")
    p = build_platform(settings=s)
    assert p.skill_store is not None
    assert "read_skill_file" in p.tools.names()
    assert "dispatch_ready" in p.named_preconditions
    assert "expedite_valid" in p.named_preconditions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scheduling_platform && pytest tests/test_skills.py::test_bootstrap_wires_skill_store_and_tool -v`
Expected: FAIL — `Platform` 无 `skill_store` 属性 / `Settings` 无 `skills_dir`

- [ ] **Step 3: Implement** — `config.py` 加字段(在 `sessions_dir` 附近):

```python
skills_dir: Path = Field(default_factory=lambda: project_root() / "data" / "skills")
```

— `bootstrap.py`:
1. 顶部 import:`from scheduling_platform.skills.store import SkillStore`、`from scheduling_platform.skills.schemas import SkillMeta`(如需)、`from scheduling_platform.engines.scheduling.preconditions import make_dispatch_precondition, make_expedite_precondition`。
2. 在 `kitting`、`followups`、`adapter` 构造**之后**(它们在 `tools` 构造之前),加:

```python
named_preconditions: dict[str, Precondition] = {
    "dispatch_ready": make_dispatch_precondition(kitting, adapter),
    "expedite_valid": make_expedite_precondition(kitting, followups),
}
```
(`Precondition` 从 `scheduling_platform.foundation.tools.registry import Precondition` 导入。)

3. 在 `tools = build_tool_registry(...)` / `register_builtin_tools(...)` **之后**(builtin 工具已注册),构造 store 并注册 `read_skill_file`:

```python
skill_store = SkillStore(settings.skills_dir)

def _read_skill_file(skill_name: str, path: str) -> dict:
    return skill_store.read_attachment(skill_name, path)

tools.register(
    name="read_skill_file",
    description="读取当前技能包的附属文件(参考资料/模板)。仅在技能执行体内有意义。",
    params={
        "type": "object",
        "properties": {
            "skill_name": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["skill_name", "path"],
    },
    handler=_read_skill_file,
    kind="read",
)
```

4. `Platform` dataclass(在 `bootstrap.py:61-80`)加字段:

```python
skill_store: SkillStore
named_preconditions: dict
```
并在 `build_platform()` 返回 `Platform(...)` 时传入 `skill_store=skill_store, named_preconditions=named_preconditions`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scheduling_platform && pytest tests/test_skills.py::test_bootstrap_wires_skill_store_and_tool -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/config.py scheduling_platform/src/scheduling_platform/bootstrap.py scheduling_platform/tests/test_skills.py
git commit -m "feat(skills): config.skills_dir + bootstrap 装配 SkillStore/read_skill_file/named_preconditions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 2.2: 三个 HTTP 端点 + ChatRequest/ChatStreamRequest 加 `skill_id`

**Files:**
- Modify: `scheduling_platform/src/scheduling_platform/main.py`(照 `/knowledge` `main.py:457-467` 模式;`ChatRequest` `:54`、`ChatStreamRequest` `:64`)
- Test: `scheduling_platform/tests/test_skills.py`(追加 TestClient 烟测)

**Interfaces:**
- Produces: `GET /skills`、`POST /skills/import`(201)、`DELETE /skills/{name}`;`ChatRequest.skill_id`、`ChatStreamRequest.skill_id`(本期仅加字段,透传到 orchestrator 在 Phase 3)。

- [ ] **Step 1: Write the failing tests** (追加)

```python
from fastapi.testclient import TestClient
from scheduling_platform.main import app, _MAX_UPLOAD_BYTES


def _client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(llm_api_key="", audit_log_file=None,
                 sessions_dir=tmp_path / "sessions", skills_dir=tmp_path / "skills")
    app.state.platform = build_platform(settings=s)
    return TestClient(app)


_DEMO_MD = """---
name: capacity-report
display_name: 产能日报
description: 汇总当日产能
allowed_tools: [query_orders]
---
你是产能分析技能。"""


def test_skills_endpoint_import_list_delete(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/skills").json() == {"skills": []}
    r = c.post("/skills/import", files={"file": ("cap.md", _DEMO_MD.encode(), "text/markdown")})
    assert r.status_code == 201
    assert r.json()["name"] == "capacity-report"
    skills = c.get("/skills").json()["skills"]
    assert len(skills) == 1 and skills[0]["display_name"] == "产能日报"
    d = c.delete("/skills/capacity-report")
    assert d.json() == {"deleted": True, "name": "capacity-report"}


def test_skills_import_duplicate_409(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/skills/import", files={"file": ("cap.md", _DEMO_MD.encode(), "text/markdown")})
    r = c.post("/skills/import", files={"file": ("cap.md", _DEMO_MD.encode(), "text/markdown")})
    assert r.status_code == 409


def test_skills_import_unknown_tool_422(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bad = _DEMO_MD.replace("[query_orders]", "[nope_tool]")
    r = c.post("/skills/import", files={"file": ("cap.md", bad.encode(), "text/markdown")})
    assert r.status_code == 422


def test_skills_import_bad_suffix_415(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/skills/import", files={"file": ("cap.txt", b"x", "text/plain")})
    assert r.status_code == 415


def test_skills_import_too_large_413(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    big = b"x" * (_MAX_UPLOAD_BYTES + 1)
    r = c.post("/skills/import", files={"file": ("cap.md", big, "text/markdown")})
    assert r.status_code == 413
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v -k endpoint or 422 or 415 or 413 or 409`
Expected: FAIL — 路由不存在(404)

- [ ] **Step 3: Implement** — `main.py`:
1. import:`from scheduling_platform.skills.parser import extract_package, validate_allowed_tools`、`from scheduling_platform.skills.schemas import SkillMeta, SkillValidationError`、`from scheduling_platform.foundation.tools.builtin import QUERY_READONLY_TOOLS`、`from datetime import datetime, timezone`。
2. `ChatRequest`(`main.py:54`)加 `skill_id: str | None = None`;`ChatStreamRequest`(`main.py:64`)同样。
3. 加端点(放 `/knowledge` 端点附近):

```python
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/skills")
async def list_skills():
    return {"skills": [m.model_dump() for m in app.state.platform.skill_store.list_all()]}


@app.post("/skills/import", status_code=201)
async def import_skill(file: UploadFile = File(...)):
    platform = app.state.platform
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "文件超过 10MB 上限")
    filename = file.filename or ""
    if not (filename.lower().endswith(".md") or filename.lower().endswith(".zip")):
        raise HTTPException(415, "仅支持 .md / .zip 后缀")
    try:
        fm, body, attachments = extract_package(data, filename)
        allowed = validate_allowed_tools(
            fm,
            set(platform.tools.names()),
            list(QUERY_READONLY_TOOLS),
            set(platform.named_preconditions.keys()),
        )
    except SkillValidationError as e:
        raise HTTPException(422, str(e)) from e
    meta = SkillMeta(
        **{**fm.model_dump(), "allowed_tools": allowed},
        file_count=len(attachments),
        bytes=len(data),
        added_at=_now_iso(),
    )
    try:
        platform.skill_store.save(meta, body, attachments)
    except KeyError:
        raise HTTPException(409, f"技能 {meta.name} 已存在")
    return meta


@app.delete("/skills/{name}")
async def delete_skill(name: str):
    if not app.state.platform.skill_store.delete(name):
        raise HTTPException(404, f"技能 {name} 不存在")
    return {"deleted": True, "name": name}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skills.py -v`
Expected: PASS (全 Phase 1+2)

- [ ] **Step 5: Manual smoke + commit**

```bash
# 启动后端,手动导入(可选,需 demo 文件,见 Task 5.1)
# curl -F "file=@docs/skills-design-v1.md" :8000/skills/import  # 仅作格式参考
git add scheduling_platform/src/scheduling_platform/main.py scheduling_platform/tests/test_skills.py
git commit -m "feat(skills): GET/POST/DELETE /skills 端点 + ChatRequest.skill_id 字段

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Phase 3: 执行 + 路由

### Task 3.1: `AgentLoop.extra_preconditions` — 技能级追加断言

**Files:**
- Modify: `scheduling_platform/src/scheduling_platform/engines/scheduling/agent_loop.py`(`__init__` `:77-86` 加参数;`_handle_call` `:212-221` 之后插入)
- Test: `scheduling_platform/tests/test_skill_routing.py`(新建)

**Interfaces:**
- Consumes: `Precondition`、`PreconditionResult`(`foundation/tools/registry.py`)。
- Produces: `AgentLoop.__init__(..., extra_preconditions: dict[str, list[Precondition]] | None = None)`;`_handle_call` 在内置 precondition 块(`:212-221`)之后、`execute`(`:223`)之前执行追加断言。

- [ ] **Step 1: Write the failing tests** (`tests/test_skill_routing.py`)

```python
from conftest import FakeLLM
from scheduling_platform.engines.scheduling.agent_loop import AgentLoop
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import PendingActionStore
from scheduling_platform.foundation.tools.registry import ToolRegistry, PreconditionResult


async def _blocking(args):
    return PreconditionResult(False, "技能禁止")


async def _ok(args):
    return {"ok": True}


def _loop(extra):
    tools = ToolRegistry()
    tools.register("query_orders", "查询订单", {"type": "object", "properties": {}}, _ok, kind="read")
    llm = FakeLLM(chat_script=[[("query_orders", {})], "最终结论"])
    return AgentLoop(
        llm, tools, PendingActionStore(), AuditLog(file_path=None),
        "", ["query_orders"], 5, extra_preconditions=extra,
    )


async def test_extra_preconditions_block():
    r = await _loop({"query_orders": [_blocking]}).run("t")
    assert r.steps[0].blocked is True
    assert "技能前置断言未通过" in r.steps[0].observation["blocked"]


async def test_extra_preconditions_none_unchanged():
    r = await _loop(None).run("t")
    assert r.steps[0].blocked is False
    assert r.answer == "最终结论"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py -v`
Expected: FAIL — `AgentLoop.__init__()` got unexpected keyword `extra_preconditions`

- [ ] **Step 3: Implement** — `agent_loop.py`:
1. `__init__` 签名末尾加:`extra_preconditions: dict[str, list[Precondition]] | None = None`;方法体加 `self._extra = extra_preconditions`。(导入 `Precondition` 从 `scheduling_platform.foundation.tools.registry`。)
2. `_handle_call` 中,在内置 precondition 块(`:212-221`,即 `if tool.kind == "write" and tool.precondition is not None: ...`)之后、`try: return await self._tools.execute(...)`(`:223`)之前,插入:

```python
        # 护栏 4b: 技能级追加断言 (只叠加, 不替换)
        if self._extra is not None:
            for pre in self._extra.get(name, []):
                result = await pre(args)
                if not result.ok:
                    self._audit.record(
                        actor="scheduling_agent",
                        action=f"skill_precondition_blocked:{name}",
                        params=args,
                        result={"reason": result.reason},
                    )
                    return {"blocked": f"技能前置断言未通过: {result.reason}"}, True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py tests/test_router.py -v`
Expected: PASS(新 2 个 + 既有 router 全绿,证 None 不影响现有路径)

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/engines/scheduling/agent_loop.py scheduling_platform/tests/test_skill_routing.py
git commit -m "feat(skills): AgentLoop 加 extra_preconditions (技能级追加断言, 只叠加不替换)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3.2: `skills/engine.py` — SkillEngine(组装 AgentLoop 执行技能)

**Files:**
- Create: `scheduling_platform/src/scheduling_platform/skills/engine.py`
- Test: `scheduling_platform/tests/test_skill_routing.py`(追加)

**Interfaces:**
- Consumes: `SkillStore`(Task 1.3)、`AgentLoop`(Task 3.1)、`EngineResponse`(`engines/base.py:30`)、`named_preconditions: dict[str, Precondition]`。
- Produces: `SkillEngine(llm, tools, pending, audit, store, settings, named_preconditions)`;`async handle(skill_id, message, session_id, history=None, on_progress=None) -> EngineResponse`。

- [ ] **Step 1: Write the failing tests** (追加到 `test_skill_routing.py`)

```python
from scheduling_platform.skills.store import SkillStore
from scheduling_platform.skills.schemas import SkillMeta
from scheduling_platform.skills.engine import SkillEngine
from scheduling_platform.config import Settings
from pathlib import Path


def _engine(tmp_path, llm, named=None):
    store = SkillStore(tmp_path / "skills")
    s = Settings(llm_api_key="", mock_data_dir=tmp_path / "mock", audit_log_file=None)
    return SkillEngine(llm, _tools_with_query_orders(), PendingActionStore(),
                      AuditLog(file_path=None), store, s, named or {})


def _tools_with_query_orders():
    tools = ToolRegistry()
    tools.register("query_orders", "查询订单", {"type": "object", "properties": {}}, _ok, kind="read")
    return tools


def _seed(store, name="cap", body="你是产能技能。", **kw):
    store.save(SkillMeta(name=name, description="x", added_at="t",
                         file_count=0, bytes=0, **kw), body, {})


async def test_skill_engine_not_found(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=["x"]))
    r = await e.handle("nope", "msg", "s1")
    assert "不存在" in r.reply


async def test_skill_engine_llm_unavailable(tmp_path):
    e = _engine(tmp_path, FakeLLM())  # available=False
    _seed(e._store, "cap")
    r = await e.handle("cap", "msg", "s1")
    assert "LLM 未配置" in r.reply


async def test_skill_engine_executes(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=["产能结论"]))
    _seed(e._store, "cap")
    r = await e.handle("cap", "msg", "s1")
    assert r.reply == "产能结论"


async def test_skill_engine_precondition_blocks(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=[[("query_orders", {})], "结论"]),
                named={"my_assert": _blocking})
    _seed(e._store, "cap", allowed_tools=["query_orders"],
          tool_preconditions={"query_orders": ["my_assert"]})
    r = await e.handle("cap", "msg", "s1")
    assert r.data["steps"][0]["blocked"] is True
    assert "技能前置断言未通过" in r.data["steps"][0]["observation"]["blocked"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py -v -k skill_engine`
Expected: FAIL — `ImportError: ...engine`

- [ ] **Step 3: Write minimal implementation** (`skills/engine.py`)

```python
from __future__ import annotations
from scheduling_platform.engines.base import EngineResponse, ProgressFn
from scheduling_platform.engines.scheduling.agent_loop import AgentLoop
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import PendingActionStore
from scheduling_platform.foundation.llm import LLMClient, LLMError
from scheduling_platform.foundation.tools.registry import ToolRegistry, Precondition
from scheduling_platform.skills.store import SkillStore

SKILL_PREAMBLE = (
    "你是技能执行体。严格按下方 SKILL.md 正文步骤推进，只用允许的工具查证/操作，"
    "不要臆造数据；写操作被护栏拦截时如实说明原因。\n\n---\n\n"
)


class SkillEngine:
    def __init__(self, llm, tools, pending, audit, store, settings,
                 named_preconditions: dict[str, Precondition]):
        self._llm = llm
        self._tools = tools
        self._pending = pending
        self._audit = audit
        self._store = store
        self._settings = settings
        self._named = named_preconditions

    async def handle(
        self, skill_id: str, message: str, session_id: str,
        history: list[dict] | None = None, on_progress: ProgressFn | None = None,
    ) -> EngineResponse:
        meta = self._store.get(skill_id)
        if meta is None:
            return EngineResponse(reply=f"技能 {skill_id} 不存在或已被删除")
        if not self._llm.available:
            return EngineResponse(reply="LLM 未配置，技能暂不可用")
        allowed = list(meta.allowed_tools or [])
        if meta.file_count > 0:
            allowed.append("read_skill_file")
        extra = {
            tool: [self._named[n] for n in names]
            for tool, names in meta.tool_preconditions.items()
        }
        body = self._store.get_body(skill_id)
        try:
            result = await AgentLoop(
                self._llm, self._tools, self._pending, self._audit,
                SKILL_PREAMBLE + body, allowed, self._settings.react_max_steps,
                extra_preconditions=extra or None,
            ).run(message, history=history, on_progress=on_progress)
        except LLMError:
            return EngineResponse(reply="LLM 调用失败，技能暂不可用")
        return EngineResponse(
            reply=result.answer,
            data={
                "steps": [s.model_dump(mode="json") for s in result.steps],
                "stop_reason": result.stop_reason,
            },
            pending_actions=result.pending_actions,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/skills/engine.py scheduling_platform/tests/test_skill_routing.py
git commit -m "feat(skills): SkillEngine 组装 AgentLoop 执行技能 (含 tool_preconditions 装配)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3.3: bootstrap 装配 SkillEngine + Orchestrator(skill_engine) + Platform 字段

**Files:**
- Modify: `scheduling_platform/src/scheduling_platform/bootstrap.py`(构造 SkillEngine;wire EmbeddingRouter/IntentRouter/Orchestrator 加 `skills=store`/`skill_engine`;`Platform` 加 `skill_engine` 字段)
- Modify: `scheduling_platform/src/scheduling_platform/orchestrator/orchestrator.py`(`__init__` 加 `skill_engine`;`_dispatch` 加 skill 分支)
- Test: `scheduling_platform/tests/test_skill_routing.py`(追加)

**Interfaces:**
- Produces: `Platform.skill_engine: SkillEngine`;`Orchestrator.__init__(..., skill_engine)`;`_dispatch` skill 分支调 `self._skills.handle(skill_id, message, session_id, history=state.history[:-1], on_progress=on_progress)`。注:EmbeddingRouter/IntentRouter 的 `skills=store` 参数在 Task 3.5/3.6 落地,本任务先透传占位(构造时先不传 skills,确保不破坏;3.5/3.6 再加)。

> **说明:** 为避免 Phase 3 中段编译断裂,本任务在 bootstrap 构造 SkillEngine 并注入 Orchestrator,但 EmbeddingRouter/IntentRouter 的 `skills` 形参在 Task 3.5/3.6 才加入(届时构造处再补 `skills=store`)。Orchestrator 的 forced/dispatch/record 改动在 Task 3.7。

- [ ] **Step 1: Write the failing test** (追加)

```python
from scheduling_platform.bootstrap import build_platform


async def test_bootstrap_wires_skill_engine(tmp_path, settings):
    p = build_platform(settings=Settings(llm_api_key="", mock_data_dir=tmp_path/"mock",
                                         audit_log_file=None, skills_dir=tmp_path/"skills"))
    assert p.skill_engine is not None
    # 技能不存在 → 友好回复(不抛)
    r = await p.skill_engine.handle("nope", "msg", "s1")
    assert "不存在" in r.reply
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py::test_bootstrap_wires_skill_engine -v`
Expected: FAIL — `Platform` 无 `skill_engine`

- [ ] **Step 3: Implement**
- `bootstrap.py`:import `SkillEngine`;在 `skill_store` 构造后(Task 2.1)加 `skill_engine = SkillEngine(llm, tools, pending, audit, skill_store, settings, named_preconditions)`;构造 `Orchestrator(..., skill_engine=skill_engine)`;`Platform` dataclass 加 `skill_engine: SkillEngine` 并在返回时传入。
- `orchestrator.py`:`__init__`(`:45-63`)加 `skill_engine: "SkillEngine"` 参数(为避免循环 import,用 `TYPE_CHECKING` 或直接 `Any`,局部 `from scheduling_platform.skills.engine import SkillEngine` 在 `if TYPE_CHECKING` 下);`self._skills = skill_engine`。
- `_dispatch`(`:152-177`):在 query 分支之前加 skill 分支:

```python
        if decision.intent == "skill":
            # 技能不拥有 Context Panel，不调 set_engine；历史去掉末条作上下文
            return await self._skills.handle(
                decision.skill_id, message, session_id,
                history=state.history[:-1], on_progress=on_progress,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py tests/test_router.py tests/test_skills.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/bootstrap.py scheduling_platform/src/scheduling_platform/orchestrator/orchestrator.py scheduling_platform/tests/test_skill_routing.py
git commit -m "feat(skills): bootstrap 装配 SkillEngine + Orchestrator _dispatch skill 分支

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3.4: `RouteDecision` 加 `"skill"` intent + `skill_id` 字段

**Files:**
- Modify: `scheduling_platform/src/scheduling_platform/orchestrator/schemas.py`(`:17-23`)
- Test: `scheduling_platform/tests/test_skill_routing.py`(追加)

**Interfaces:**
- Produces: `RouteDecision.intent` 加 `"skill"`;`RouteDecision.skill_id: str | None = None`。`llm.classify` 注入 `model_json_schema()` → LLM 自动可填,`classify` 本身零改动。

- [ ] **Step 1: Write the failing test** (追加)

```python
from scheduling_platform.orchestrator.schemas import RouteDecision


def test_routedecision_skill_fields():
    d = RouteDecision(intent="skill", skill_id="cap", confidence=0.9)
    assert d.intent == "skill" and d.skill_id == "cap"
    schema = RouteDecision.model_json_schema()
    assert "skill" in schema["properties"]["intent"]["enum"]
    assert "skill_id" in schema["properties"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py::test_routedecision_skill_fields -v`
Expected: FAIL — `"skill"` 非合法 intent / 无 `skill_id`

- [ ] **Step 3: Implement** — `schemas.py`:`intent` Literal 加 `"skill"`;新增字段 `skill_id: str | None = None`(放 `reason` 之后或 `steps` 之前,位置不限,有默认值即向后兼容)。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py tests/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/orchestrator/schemas.py scheduling_platform/tests/test_skill_routing.py
git commit -m "feat(skills): RouteDecision 加 skill intent + skill_id 字段

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3.5: `EmbeddingRouter` — 技能向量 + version 拉式失效(分叉 A1)

**Files:**
- Modify: `scheduling_platform/tests/conftest.py`(`_EMBED_VOCAB` 补技能判别词)
- Modify: `scheduling_platform/src/scheduling_platform/orchestrator/embedding_router.py`(`__init__` 加 `skills`;`_ensure_vectors` 末尾调 `_ensure_skill_vectors`;新增 `_ensure_skill_vectors`)
- Test: `scheduling_platform/tests/test_skill_routing.py`(追加)

**Interfaces:**
- Produces: `EmbeddingRouter(llm, examples=None, skills: SkillStore | None = None)`;`classify` 返回的 `EmbedResult.intent` 可能是 `"skill:{name}"`(由 `_vectors` 含 skill 键自然产出);按 `store.version` 失效重嵌。

- [ ] **Step 1: Write the failing tests** (追加;`EXAMPLES` 局部定义)

```python
from scheduling_platform.orchestrator.embedding_router import EmbeddingRouter

EXAMPLES = {
    "planning": ["重新排产", "优化排程"],
    "scheduling": ["把任务令下发了", "催一下缺料"],
    "query": ["查库存还有多少"],
}


def _seed_skill(store, name="capacity-report", when=("给我出一份今天的产能报告",)):
    store.save(SkillMeta(name=name, description="产能日报", when_to_use=list(when),
                        added_at="t", file_count=0, bytes=0), "正文", {})


async def test_embedding_classifies_skill(tmp_path):
    store = SkillStore(tmp_path / "skills")
    _seed_skill(store)
    er = EmbeddingRouter(FakeLLM(embed=True), EXAMPLES, skills=store)
    result = await er.classify("出一份产能报告")
    assert result.intent == "skill:capacity-report"
    assert result.score >= 0.5


async def test_embedding_skill_version_invalidation(tmp_path):
    store = SkillStore(tmp_path / "skills")
    er = EmbeddingRouter(FakeLLM(embed=True), EXAMPLES, skills=store)
    r1 = await er.classify("重新排产")  # 无技能 → planning
    assert r1.intent == "planning"
    _seed_skill(store, when=("出产能报告",))
    r2 = await er.classify("出产能报告")  # 导入后 version 变 → 重嵌 → 命中 skill
    assert r2.intent == "skill:capacity-report"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py -v -k embedding`
Expected: FAIL — `EmbeddingRouter()` 不接受 `skills` / "产能" 不在 vocab 不命中

- [ ] **Step 3: Implement**
- `conftest.py` `_EMBED_VOCAB`(在 query 行后)追加技能判别词:

```python
    "产能", "报告", "日报", "瓶颈",  # skill
```

- `embedding_router.py` `__init__` 加 `skills` 参数:

```python
    def __init__(self, llm, examples: dict[str, list[str]] | None = None,
                 skills=None):
        self._llm = llm
        self._examples = examples or {}
        self._vectors: dict[str, list[list[float]]] | None = None
        self._skills = skills
        self._skill_version: int | None = None
```

- `_ensure_vectors` 末尾(`self._vectors = store` 之后,方法 return 之前)加 `await self._ensure_skill_vectors()`,并新增方法:

```python
    async def _ensure_skill_vectors(self) -> None:
        assert self._vectors is not None
        if self._skills is None or self._skill_version == self._skills.version:
            return
        for k in [k for k in self._vectors if k.startswith("skill:")]:
            del self._vectors[k]
        examples = self._skills.routing_examples()
        if examples:
            flat = [(intent, s) for intent, sents in examples.items() for s in sents]
            vecs = await self._llm.embed([s for _, s in flat])
            for (intent, _), v in zip(flat, vecs):
                self._vectors.setdefault(intent, []).append(v)
        self._skill_version = self._skills.version
        logger.info("[EMBED] 技能例句已向量化 (version=%d)", self._skill_version)
```

(`SkillStore` 仅作类型提示用 `skills=None` 不强注类型,避免循环 import;或顶部 `from __future__ import annotations` + 字符串注解。)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py tests/test_router.py -v`
Expected: PASS(技能向量 + 既有 embedding 测试不回归)

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/tests/conftest.py scheduling_platform/src/scheduling_platform/orchestrator/embedding_router.py scheduling_platform/tests/test_skill_routing.py
git commit -m "feat(skills): EmbeddingRouter 吃技能 when_to_use 向量 + version 拉式失效 (分叉 A1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3.6: `_classify_system` 候选拼接 + `IntentRouter` 技能路由与校验(分叉 B1)

**Files:**
- Modify: `scheduling_platform/src/scheduling_platform/orchestrator/router.py`(`CLASSIFY_SYSTEM` → 保留为常量 + 新增 `_classify_system` 构造函数;`IntentRouter.__init__` 加 `skills`;`route()` embedding 分支拆 skill 前缀、LLM 分支校验 skill_id)
- Modify: `scheduling_platform/src/scheduling_platform/bootstrap.py`(构造处补 `skills=skill_store`)
- Test: `scheduling_platform/tests/test_skill_routing.py`(追加)

**Interfaces:**
- Produces: `IntentRouter(llm, settings, embed_router=None, skills: SkillStore | None = None)`;`_classify_system(skill_candidates: list[tuple[str,str]]) -> str`(无技能时逐字节等于 `CLASSIFY_SYSTEM`);embedding 命中 `skill:{name}` → `RouteDecision(intent="skill", skill_id=name)`;LLM 返回 `intent="skill"` 但 `skill_id` ∉ routable → 降 `ambiguous`。

- [ ] **Step 1: Write the failing tests** (追加)

```python
from scheduling_platform.orchestrator.router import IntentRouter


def _router(llm, store, settings):
    embed = EmbeddingRouter(llm, EXAMPLES, skills=store) if llm.embed_available else None
    return IntentRouter(llm, settings, embed, skills=store)


async def test_llm_routes_to_existing_skill(tmp_path, settings):
    store = SkillStore(tmp_path / "skills")
    _seed_skill(store)
    llm = FakeLLM(classify_map={
        RouteDecision: RouteDecision(intent="skill", skill_id="capacity-report",
                                     confidence=0.9, reason="LLM"),
    }, embed=False)
    d = await _router(llm, store, settings).route("弄一下产能")
    assert d.intent == "skill" and d.skill_id == "capacity-report"
    assert d.route_method == "llm"


async def test_llm_skill_nonexistent_degrades_ambiguous(tmp_path, settings):
    store = SkillStore(tmp_path / "skills")  # 空
    llm = FakeLLM(classify_map={
        RouteDecision: RouteDecision(intent="skill", skill_id="ghost", confidence=0.9),
    }, embed=False)
    d = await _router(llm, store, settings).route("弄一下")
    assert d.intent == "ambiguous"
    assert "不存在的技能" in d.reason


async def test_embedding_routes_to_skill(tmp_path, settings):
    store = SkillStore(tmp_path / "skills")
    _seed_skill(store)
    d = await _router(FakeLLM(embed=True), store, settings).route("出一份产能报告")
    assert d.intent == "skill" and d.skill_id == "capacity-report"
    assert d.route_method == "embedding"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py -v -k llm_routes or llm_skill_nonexistent or embedding_routes_to_skill`
Expected: FAIL — `IntentRouter()` 不接受 `skills` / skill 前缀未拆

- [ ] **Step 3: Implement** — `router.py`:
1. 保留 `CLASSIFY_SYSTEM` 常量不动;新增模块级函数:

```python
def _classify_system(skill_candidates: list[tuple[str, str]]) -> str:
    if not skill_candidates:
        return CLASSIFY_SYSTEM
    block = "\n".join(f"- skill:{name}: {desc}" for name, desc in skill_candidates)
    return (
        CLASSIFY_SYSTEM
        + "\n\n此外有可路由的「技能(skill)」用于长尾流程化任务:\n"
        + block
        + '\n若匹配某技能，intent 填 "skill"，skill_id 填该技能 name。'
    )
```

2. `IntentRouter.__init__` 加 `skills=None` 参数 → `self._skills = skills`;新增:

```python
    def _skill_candidates(self) -> list[tuple[str, str]]:
        if self._skills is None:
            return []
        return [(m.name, m.description) for m in self._skills.routable()]
```

3. `route()` embedding 分支(`:91-100` 的 `return RouteDecision(intent=result.intent, ...)` 之前)加 skill 前缀拆解:

```python
                    if result.intent.startswith("skill:"):
                        return RouteDecision(
                            intent="skill",
                            skill_id=result.intent.split(":", 1)[1],
                            confidence=round(result.score, 3),
                            entities=entities,
                            reason=f"嵌入语义路由 (score={result.score:.2f})",
                            route_method="embedding",
                        )
```

4. `route()` LLM 分支:把 `CLASSIFY_SYSTEM`(`:112`)换成 `_classify_system(self._skill_candidates())`;在 `decision.route_method = "llm"`(`:114`)之后、`return decision`(`:121`)之前加校验:

```python
                if decision.intent == "skill" and self._skills is not None:
                    routable_names = {m.name for m in self._skills.routable()}
                    if decision.skill_id not in routable_names:
                        decision = RouteDecision(
                            intent="ambiguous", confidence=0.0,
                            entities=decision.entities,
                            reason=f"LLM 选择了不存在的技能 {decision.skill_id}",
                            route_method="llm",
                        )
```

- `bootstrap.py`:构造 `EmbeddingRouter(llm, examples, skills=skill_store)`、`IntentRouter(llm, settings, embed_router, skills=skill_store)`(Task 3.3 已构造 store,此处补 `skills=` 透传)。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py tests/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduling_platform/src/scheduling_platform/orchestrator/router.py scheduling_platform/src/scheduling_platform/bootstrap.py scheduling_platform/tests/test_skill_routing.py
git commit -m "feat(skills): _classify_system 候选拼接 + IntentRouter skill 路由/校验 (分叉 B1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3.7: Orchestrator forced/dispatch/record + `_contract_route` + chat 透传

**Files:**
- Modify: `scheduling_platform/src/scheduling_platform/orchestrator/orchestrator.py`(`handle` 加 `skill_id` + forced 分支;`_gate_and_dispatch` 门控加 `"skill"`;`_record_route` 加 `skill_id`)
- Modify: `scheduling_platform/src/scheduling_platform/main.py`(`_contract_route` `:131-141` 加 `skill_id`;`/chat` `:94-96`、`/chat/stream` `:216-221` 透传)
- Test: `scheduling_platform/tests/test_skill_routing.py`(追加)

**Interfaces:**
- Produces: `Orchestrator.handle(..., skill_id: str | None = None)`;forced skill → `RouteDecision(intent="skill", skill_id=…, route_method="forced", confidence=1.0)`;SSE `route` 帧 payload 加 `skill_id`(非技能为 null)。

- [ ] **Step 1: Write the failing tests** (追加)

```python
from scheduling_platform.main import app, _contract_route
from fastapi.testclient import TestClient


async def test_orchestrator_forced_skill(tmp_path):
    s = Settings(llm_api_key="", mock_data_dir=tmp_path / "mock",
                 audit_log_file=None, skills_dir=tmp_path / "skills")
    p = build_platform(settings=s, llm=FakeLLM(chat_script=["产能结论"]))
    _seed_skill(p.skill_store)
    resp = await p.orchestrator.handle("s1", "出产能报告", skill_id="capacity-report")
    assert resp.reply == "产能结论"
    assert resp.route.intent == "skill"
    assert resp.route.skill_id == "capacity-report"
    assert resp.route.route_method == "forced"


def test_contract_route_emits_skill_id():
    rd = RouteDecision(intent="skill", skill_id="cap", confidence=1.0, route_method="forced")
    out = _contract_route(rd)
    assert out["intent"] == "skill"
    assert out["skill_id"] == "cap"
    assert _contract_route(RouteDecision(intent="planning", confidence=0.9))["skill_id"] is None


async def test_chat_endpoint_threads_skill_id(tmp_path, monkeypatch):
    s = Settings(llm_api_key="", mock_data_dir=tmp_path / "mock",
                 audit_log_file=None, skills_dir=tmp_path / "skills")
    p = build_platform(settings=s, llm=FakeLLM(chat_script=["产能结论"]))
    _seed_skill(p.skill_store)
    app.state.platform = p
    c = TestClient(app)
    r = c.post("/chat", json={"session_id": "s1", "message": "出产能报告",
                              "skill_id": "capacity-report"})
    assert r.status_code == 200
    body = r.json()
    assert body["route"]["intent"] == "skill"
    assert body["route"]["skill_id"] == "capacity-report"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scheduling_platform && pytest tests/test_skill_routing.py -v -k forced_skill or contract_route or chat_endpoint`
Expected: FAIL — `handle()` 不接受 `skill_id` / `_contract_route` 无 `skill_id`

- [ ] **Step 3: Implement**
- `orchestrator.py` `handle`(`:65-71`)签名加 `skill_id: str | None = None`;在 `state = self._memory.get(session_id)`(`:72`)之后、现有 `if route in (...)`(`:75`)之前加 forced 分支:

```python
        if skill_id is not None:
            decision = RouteDecision(
                intent="skill", skill_id=skill_id, confidence=1.0,
                entities=extract_entities(message), reason="前端选定技能",
                route_method="forced",
            )
            self._memory.append(session_id, "user", message)
            self._record_route(session_id, message, decision)
            resp = await self._dispatch(decision, message, session_id, state, on_progress)
            return self._finish(session_id, decision, resp)
```

- `_gate_and_dispatch` 门控元组(`:140`)加 `"skill"`:`if decision.intent in ("planning", "scheduling", "query", "skill") and decision.confidence >= threshold:`。
- `_record_route` 的 `result` dict(`:189-194`)加 `"skill_id": decision.skill_id`。
- `main.py` `_contract_route`(`:131-141`)输出加 `"skill_id": rd.skill_id if rd.intent == "skill" else None`。
- `/chat`(`:94-96`):`orchestrator.handle(req.session_id, req.message, route=req.route, skill_id=req.skill_id)`。
- `/chat/stream`(`:216-221`):`platform.orchestrator.handle(req.session_id, req.message, route=req.current_engine or "auto", on_progress=progress_q.put, skill_id=req.skill_id)`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scheduling_platform && pytest -v`
Expected: PASS(全后端测试不回归)

- [ ] **Step 5: Manual smoke + commit**

```bash
# 可选端到端(需后端在跑):导入 demo 技能 → 发送带 skill_id 的 /chat/stream → 观察 route 帧 intent:"skill"
git add scheduling_platform/src/scheduling_platform/orchestrator/orchestrator.py scheduling_platform/src/scheduling_platform/main.py scheduling_platform/tests/test_skill_routing.py
git commit -m "feat(skills): Orchestrator forced/dispatch/record + _contract_route skill_id + chat 透传

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Phase 4: 前端

> 前端验证基线(代码现实):`ROUTE_META` 在 `lib/routes.ts:25-66`,`RouteMeta` 字段 `{zh,en,dot,leftBorder,fg,tintBg,border,glow}`;`RouteEngine` 在 `types/index.ts:12`;`OpenMenu` 在 `Composer.tsx:69`,chip 工厂 `:114-117`,`toolbarRef` `:82`,`ROUTE_OPTS` `:38-49`;Workspace route/mode state `:55/:68`,`handleRouteChange` `:63-67`,`onSend` `:238`;`useOrchestrator.send` `:87`,`useStreamingChat.send` `:133`(body `:137`);`types/api.ts` `IntentType` `:15`、`RouteDecision` `:44`、`ChatStreamRequest` `:61`;knowledge `api/knowledge.ts`、`queryKeys.ts:18`、`hooks.ts:165`、`apiUpload` 在 `client.ts:125`、`UploadZone.tsx`、`shared.ts`(errMessage/extOf)、`UploadProgress.tsx:9`(硬编 `bg-query`);MSW `handlers.ts:260`/`fixtures.ts`;`Popover`/`ProgressBar` 在 `components/ui/`,**无 Modal**。`npm test` = vitest。

### Task 4.1: 类型扩展

**Files:**
- Modify: `frontend/src/types/api.ts`、`frontend/src/types/index.ts`

**Interfaces:**
- Produces: `SkillMeta`、`SkillListResponse`;`IntentType` 加 `'skill'`;`RouteDecision.skill_id?: string | null`;`ChatStreamRequest.skill_id?: string | null`;`RouteEngine` 加 `'skill'`。

- [ ] **Step 1: Implement** — `types/api.ts`:

```typescript
export interface SkillMeta {
  name: string;
  display_name?: string;
  description: string;
  when_to_use?: string[];
  allowed_tools?: string[];
  user_invocable?: boolean;
  disable_model_invocation?: boolean;
  tool_preconditions?: Record<string, string[]>;
  version?: string;
  author?: string;
  file_count: number;
  bytes: number;
  added_at: string;
}

export interface SkillListResponse {
  skills: SkillMeta[];
}
```
`IntentType`(`:15`)末尾加 `| 'skill'`;`RouteDecision`(`:44-55`)加 `skill_id?: string | null;`;`ChatStreamRequest`(`:61-66`)加 `skill_id?: string | null;`。

— `types/index.ts`:`RouteEngine`(`:12`)加 `| 'skill'`。

- [ ] **Step 2: Verify (类型改动以 tsc 通过为验证)**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS(无新增类型错误)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/types/index.ts
git commit -m "feat(skills-fe): SkillMeta 类型 + IntentType/RouteEngine/RouteDecision/ChatStreamRequest 加 skill

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4.2: 数据层 `api/skills.ts` + queryKeys + hooks

**Files:**
- Create: `frontend/src/api/skills.ts`
- Modify: `frontend/src/api/queryKeys.ts`、`frontend/src/api/hooks.ts`、`frontend/src/api/index.ts`

**Interfaces:**
- Produces: `listSkills(): Promise<SkillListResponse>`、`importSkill(file: File, onProgress?): Promise<SkillMeta>`、`deleteSkill(name: string): Promise<void>`;`useSkills`/`useImportSkill`/`useDeleteSkill`。

- [ ] **Step 1: Write the failing test** (`src/api/skills.test.ts`,照 `useStreamingChat.test.tsx` 的 vi.mock 范式)

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
vi.mock("./client", () => ({
  apiGet: vi.fn(),
  apiUpload: vi.fn(),
  apiDelete: vi.fn(),
}));
import { apiGet, apiUpload, apiDelete } from "./client";
import { listSkills, importSkill, deleteSkill } from "./skills";

describe("skills api", () => {
  beforeEach(() => vi.clearAllMocks());

  it("listSkills calls GET /skills", async () => {
    (apiGet as any).mockResolvedValue({ skills: [] });
    await listSkills();
    expect(apiGet).toHaveBeenCalledWith("/skills");
  });

  it("importSkill posts file to /skills/import", async () => {
    (apiUpload as any).mockResolvedValue({ name: "cap" });
    await importSkill(new File(["x"], "cap.md"));
    expect(apiUpload).toHaveBeenCalledWith("/skills/import", expect.any(FormData), expect.anything());
  });

  it("deleteSkill calls DELETE /skills/:name", async () => {
    (apiDelete as any).mockResolvedValue(undefined);
    await deleteSkill("cap");
    expect(apiDelete).toHaveBeenCalledWith("/skills/cap");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- skills.test`
Expected: FAIL — `./skills` 不存在

- [ ] **Step 3: Implement** — `api/skills.ts`:

```typescript
import { apiGet, apiUpload, apiDelete } from "./client";
import type { SkillListResponse, SkillMeta } from "@/types/api";

export function listSkills() {
  return apiGet<SkillListResponse>("/skills");
}

export function importSkill(file: File, onProgress?: (fraction: number) => void) {
  const fd = new FormData();
  fd.append("file", file);
  return apiUpload<SkillMeta>("/skills/import", fd, { onProgress });
}

export function deleteSkill(name: string) {
  return apiDelete<void>(`/skills/${encodeURIComponent(name)}`);
}
```

— `queryKeys.ts`(照 `knowledge` `:18-20`)加:

```typescript
  skills: {
    list: () => ["skills", "list"] as const,
  },
```

— `hooks.ts`(照 `useKnowledgeDocs`/`useUploadKnowledge` `:165-222`)加:

```typescript
export function useSkills() {
  return useQuery({ queryKey: queryKeys.skills.list(), queryFn: listSkills });
}

export function useImportSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => importSkill(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.skills.list() }),
  });
}

export function useDeleteSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => deleteSkill(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.skills.list() }),
  });
}
```

(顶部 import `listSkills, importSkill, deleteSkill` from `./skills`、`useQuery, useMutation, useQueryClient`、`queryKeys`。)

— `api/index.ts`:re-export `* from "./skills"` 及三个 hook(照 knowledge 的 re-export 行 `:22-49`)。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- skills.test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/skills.ts frontend/src/api/queryKeys.ts frontend/src/api/hooks.ts frontend/src/api/index.ts frontend/src/api/skills.test.ts
git commit -m "feat(skills-fe): 数据层 api/skills + queryKeys + hooks (useSkills/useImportSkill/useDeleteSkill)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4.3: MSW 夹具与 handlers

**Files:**
- Modify: `frontend/src/mocks/api/fixtures.ts`、`frontend/src/mocks/api/handlers.ts`

**Interfaces:**
- Produces:`GET /skills`、`POST /skills/import`、`DELETE /skills/:name` 三个 mock handler(照 knowledge `handlers.ts:260-280`)。

- [ ] **Step 1: Implement** — `fixtures.ts` 加:

```typescript
export const SKILLS = [
  { name: "capacity-report", display_name: "产能日报", description: "汇总当日产能与瓶颈",
    when_to_use: ["给我出一份今天的产能报告"], allowed_tools: ["query_orders", "query_work_orders"],
    user_invocable: true, disable_model_invocation: false, tool_preconditions: {},
    version: "1.0", author: "demo", file_count: 0, bytes: 0, added_at: "2026-07-05T00:00:00Z" },
  { name: "changeover-checklist", display_name: "换线检查清单", description: "换线前齐套与产线核对",
    when_to_use: ["3号线换线前检查"], allowed_tools: ["query_work_orders", "check_kitting"],
    user_invocable: true, disable_model_invocation: false, tool_preconditions: {},
    version: "1.0", author: "demo", file_count: 0, bytes: 0, added_at: "2026-07-05T00:00:00Z" },
];
```

— `handlers.ts`(照 knowledge 上传 handler `:260-280`)加:

```typescript
import { SKILLS } from "./fixtures";

http.get("/api/v1/skills", () => HttpResponse.json({ skills: SKILLS })),

http.post("/api/v1/skills/import", async ({ request }) => {
  const fd = await request.formData();
  const file = fd.get("file") as File;
  if (!file || !/\.(zip|md)$/i.test(file.name)) return HttpResponse.json({ detail: "仅支持 .md/.zip" }, { status: 415 });
  await delay(700);
  const meta = {
    name: file.name.replace(/\.(zip|md)$/i, ""),
    display_name: file.name.replace(/\.(zip|md)$/i, ""),
    description: "已导入技能", when_to_use: [], allowed_tools: [],
    user_invocable: true, disable_model_invocation: false, tool_preconditions: {},
    file_count: 0, bytes: file.size, added_at: new Date().toISOString(),
  };
  SKILLS.push(meta);
  return HttpResponse.json(meta, { status: 201 });
}),

http.delete("/api/v1/skills/:name", ({ params }) => {
  const idx = SKILLS.findIndex((s) => s.name === params.name);
  if (idx < 0) return HttpResponse.json({ detail: "不存在" }, { status: 404 });
  SKILLS.splice(idx, 1);
  return HttpResponse.json({ deleted: true, name: params.name });
}),
```
(用现有 `http`/`HttpResponse`/`delay` 导入;路径前缀对齐既有 handler 的 `/api/v1`。)

- [ ] **Step 2: Verify**

Run: `cd frontend && VITE_API_MOCKING=enabled npm run dev`(手动:浏览器开应用,DevTools Network 看到 GET /skills 200)
Expected: 夹具生效(手动走查;无独立 vitest,MSW handler 由集成测试覆盖)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/mocks/api/fixtures.ts frontend/src/mocks/api/handlers.ts
git commit -m "feat(skills-fe): MSW 夹具 SKILLS + GET/POST/DELETE /skills handlers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4.4: `components/ui/Modal.tsx` — 最小弹窗原语

**Files:**
- Create: `frontend/src/components/ui/Modal.tsx`

**Interfaces:**
- Produces:`<Modal open onClose title children />`(`fixed inset-0 z-[60]` + `bg-black/50` scrim + 面板 `bg-surface-1 rounded-xl border-border-default shadow-popover`;Escape/背景点击/X 关闭)。

- [ ] **Step 1: Write the failing test** (`src/components/ui/Modal.test.tsx`,照 `PendingActionsCard.test.tsx`)

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { Modal } from "./Modal";

describe("Modal", () => {
  it("renders children when open", () => {
    render(<Modal open onClose={() => {}} title="导入">内容</Modal>);
    expect(screen.getByText("内容")).toBeInTheDocument();
    expect(screen.getByText("导入")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(<Modal open={false} onClose={() => {}} title="导入">内容</Modal>);
    expect(screen.queryByText("内容")).toBeNull();
  });

  it("calls onClose on Escape and scrim click and X", () => {
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="导入">x</Modal>);
    fireEvent.keyDown(document.body, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: /关闭|×/ }));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- Modal.test`
Expected: FAIL — `./Modal` 不存在

- [ ] **Step 3: Implement** (`components/ui/Modal.tsx`)

```tsx
import { useEffect } from "react";
import { X } from "lucide-react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-[420px] max-w-[90vw] rounded-xl border border-border-default bg-surface-1 shadow-popover"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
          <span className="text-body-sm font-semibold">{title}</span>
          <button onClick={onClose} aria-label="关闭" className="text-text-tertiary hover:text-text-primary">
            <X size={16} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- Modal.test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/Modal.tsx frontend/src/components/ui/Modal.test.tsx
git commit -m "feat(skills-fe): 最小 Modal 原语 (bg-surface-1, Escape/scrim/X 关闭)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4.5: `SkillMenu.tsx` — chip + Popover

**Files:**
- Create: `frontend/src/features/orchestrator/skills/SkillMenu.tsx`、`SkillMenu.test.tsx`

**Interfaces:**
- Produces:`<SkillMenu skills skill onSkillChange onImportSkill open onToggle />`;chip 复用 Composer chip 工厂样式(`border-accent-border bg-accent-bg`),图标 `Sparkles`,文案 = `skill?.display_name ?? '技能'`;Popover 列表 + 搜索 + 清除项 + 导入入口。

- [ ] **Step 1: Write the failing test** (`SkillMenu.test.tsx`)

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { SkillMenu } from "./SkillMenu";
import { SKILLS } from "@/mocks/api/fixtures";

const props = (overrides = {}) => ({
  skills: SKILLS, skill: null, onSkillChange: vi.fn(),
  onImportSkill: vi.fn(), open: true, onToggle: vi.fn(), ...overrides,
});

describe("SkillMenu", () => {
  it("lists skills and filters by search", () => {
    render(<SkillMenu {...props()} />);
    expect(screen.getByText("产能日报")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/搜索/), { target: { value: "换线" } });
    expect(screen.queryByText("产能日报")).toBeNull();
    expect(screen.getByText("换线检查清单")).toBeInTheDocument();
  });

  it("selecting a skill calls onSkillChange", () => {
    render(<SkillMenu {...props()} />);
    fireEvent.click(screen.getByText("产能日报"));
    expect(props().onSkillChange).not.toHaveBeenCalled();
    const onChange = vi.fn();
    render(<SkillMenu {...props({ onSkillChange: onChange })} />);
    fireEvent.click(screen.getByText("产能日报"));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ name: "capacity-report" }));
  });

  it("clear and import entries", () => {
    const onSkillChange = vi.fn(), onImportSkill = vi.fn();
    render(<SkillMenu {...props({ onSkillChange, onImportSkill })} />);
    fireEvent.click(screen.getByText("不使用技能"));
    expect(onSkillChange).toHaveBeenCalledWith(null);
    fireEvent.click(screen.getByText(/导入技能/));
    expect(onImportSkill).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- SkillMenu.test`
Expected: FAIL — `./SkillMenu` 不存在

- [ ] **Step 3: Implement** (`SkillMenu.tsx`,复用 `Popover` + chip 工厂样式)

```tsx
import { useState } from "react";
import { Sparkles, Check, Search } from "lucide-react";
import type { SkillMeta } from "@/types/api";

interface SkillMenuProps {
  skills: SkillMeta[];
  skill: SkillMeta | null;
  onSkillChange: (s: SkillMeta | null) => void;
  onImportSkill: () => void;
  open: boolean;
  onToggle: () => void;
}

export function SkillMenu({ skills, skill, onSkillChange, onImportSkill, open, onToggle }: SkillMenuProps) {
  const [q, setQ] = useState("");
  const visible = skills.filter((s) => s.user_invocable !== false);
  const filtered = visible.filter((s) =>
    [s.name, s.display_name, s.description].join(" ").toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        className={`flex items-center gap-1 rounded-md border px-2 py-1 text-body-sm ${
          skill ? "border-accent-border bg-accent-bg text-accent-fg" : "border-border-default hover:bg-border-subtle"
        }`}
      >
        <Sparkles size={14} className="text-accent" />
        {skill?.display_name ?? "技能"}
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-[260px] rounded-md border border-border-default bg-surface-1 shadow-popover">
          <div className="flex items-center gap-1 border-b border-border-default px-2 py-1">
            <Search size={12} className="text-text-tertiary" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索技能"
              className="w-full bg-transparent text-body-sm placeholder:text-text-tertiary focus:outline-none"
            />
          </div>
          <div className="max-h-[280px] overflow-auto py-1">
            <button
              onClick={() => onSkillChange(null)}
              className="flex w-full items-center justify-between px-2 py-1 hover:bg-border-subtle"
            >
              <span className="text-body-sm text-text-tertiary">不使用技能</span>
              {!skill && <Check size={14} className="text-accent" />}
            </button>
            {filtered.map((s) => (
              <button
                key={s.name}
                onClick={() => onSkillChange(s)}
                className="flex w-full items-start justify-between px-2 py-1 hover:bg-border-subtle"
              >
                <span className="flex flex-col items-start">
                  <span className="text-body-sm font-semibold">{s.display_name ?? s.name}</span>
                  <span className="line-clamp-1 text-[11px] text-text-tertiary">{s.description}</span>
                </span>
                {skill?.name === s.name && <Check size={14} className="text-accent" />}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-2 py-2 text-[11px] text-text-tertiary">暂无技能，点击下方导入</div>
            )}
          </div>
          <div className="border-t border-border-default px-2 py-1">
            <button onClick={onImportSkill} className="text-body-sm text-accent hover:underline">
              导入技能…
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- SkillMenu.test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/orchestrator/skills/SkillMenu.tsx frontend/src/features/orchestrator/skills/SkillMenu.test.tsx
git commit -m "feat(skills-fe): SkillMenu chip + Popover (搜索/列表/导入入口)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4.6: `SkillImportModal.tsx` — 拖拽/点击上传

**Files:**
- Create: `frontend/src/features/orchestrator/skills/SkillImportModal.tsx`、`SkillImportModal.test.tsx`
- Modify: `frontend/src/features/query/knowledge/UploadProgress.tsx`(加 `fillClassName` prop — 见 Task 4.7,本任务消费)

**Interfaces:**
- Produces:`<SkillImportModal open onClose onImported={(s) => ...} />`;拖拽区 + 隐藏 `<input accept=".zip,.md">`;`useImportSkill` + `<UploadProgress fillClassName="bg-accent" />`;失败显示「技能包不符合规范:{errMessage(e)}」;成功回调 `onImported(meta)`。

- [ ] **Step 1: Write the failing test** (mock `useImportSkill`)

```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SkillImportModal } from "./SkillImportModal";

vi.mock("@/api", () => ({
  useImportSkill: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, error: null })),
}));
import { useImportSkill } from "@/api";

describe("SkillImportModal", () => {
  it("renders drop zone and accepts a file", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ name: "cap" });
    (useImportSkill as any).mockReturnValue({ mutateAsync, isPending: false, error: null });
    render(<SkillImportModal open onClose={() => {}} onImported={() => {}} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "cap.md")] } });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  });

  it("shows error message on failure", () => {
    (useImportSkill as any).mockReturnValue({
      mutateAsync: vi.fn(), isPending: false,
      error: { message: "skill name 重复" },
    });
    render(<SkillImportModal open onClose={() => {}} onImported={() => {}} />);
    expect(screen.getByText(/技能包不符合规范/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- SkillImportModal.test`
Expected: FAIL — `./SkillImportModal` 不存在

- [ ] **Step 3: Implement** (`SkillImportModal.tsx`,照 `UploadZone.tsx` 拖拽模式 + `shared.ts` 的 `errMessage`/`extOf`)

```tsx
import { useRef, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { UploadProgress } from "@/features/query/knowledge/UploadProgress";
import { errMessage, extOf } from "@/features/query/knowledge/shared";
import { useImportSkill } from "@/api";
import type { SkillMeta } from "@/types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: (s: SkillMeta) => void;
}

export function SkillImportModal({ open, onClose, onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fraction, setFraction] = useState(0);
  const { mutateAsync, isPending, error } = useImportSkill();

  async function upload(file: File) {
    if (!/^\.(zip|md)$/i.test(extOf(file.name))) {
      return; // 客户端预检后缀;后端兜底 415
    }
    setFraction(0);
    try {
      const meta = await mutateAsync(file);
      onImported(meta);
      onClose();
    } catch {
      // error 由 useImportSkill.error 承载
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="导入技能">
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragging(false);
          if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
        }}
        className={`cursor-pointer rounded-lg border border-dashed p-6 text-center text-body-sm ${
          dragging ? "border-accent-border bg-accent-bg" : "border-border-default"
        }`}
      >
        拖拽 .zip / .md 技能包到此，或点击选择
        <input
          ref={inputRef}
          type="file"
          accept=".zip,.md"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
      </div>
      {isPending && <UploadProgress fraction={fraction} fillClassName="bg-accent" />}
      {error && (
        <div className="mt-2 text-[12px] text-status-error">
          技能包不符合规范：{errMessage(error)}
        </div>
      )}
    </Modal>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- SkillImportModal.test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/orchestrator/skills/SkillImportModal.tsx frontend/src/features/orchestrator/skills/SkillImportModal.test.tsx
git commit -m "feat(skills-fe): SkillImportModal 拖拽/点击上传 + 错误提示

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4.7: `ROUTE_META.skill` 条目 + `UploadProgress.fillClassName`

**Files:**
- Modify: `frontend/src/lib/routes.ts`、`frontend/src/features/query/knowledge/UploadProgress.tsx`

**Interfaces:**
- Produces:`ROUTE_META.skill`(accent token 家族,`fg='text-accent-fg'`+`leftBorder='border-l-accent'`);`UploadProgress` 加 `fillClassName?: string`(默认 `bg-query`,knowledge 不动)。

- [ ] **Step 1: Implement** — `lib/routes.ts` 加(drift #2):

```typescript
  skill: {
    zh: "技能",
    en: "skill",
    dot: "bg-accent",
    leftBorder: "border-l-accent",
    fg: "text-accent-fg",
    tintBg: "bg-accent-bg",
    border: "border-accent-border",
    glow: "shadow-glow-accent",
  },
```

— `UploadProgress.tsx`(`:9` 处):

```tsx
interface UploadProgressProps {
  fraction: number;
  error?: boolean;
  fillClassName?: string; // 默认 'bg-query'，技能传 'bg-accent'
}
export function UploadProgress({ fraction, error, fillClassName = "bg-query" }: UploadProgressProps) {
  return <ProgressBar fillClassName={error ? "bg-status-error" : fillClassName} />;
}
```

- [ ] **Step 2: Verify (类型 + 既有 knowledge 测试不回归)**

Run: `cd frontend && npm test && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/routes.ts frontend/src/features/query/knowledge/UploadProgress.tsx
git commit -m "feat(skills-fe): ROUTE_META skill 条目 (accent 家族) + UploadProgress fillClassName prop

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4.8: Composer / Workspace / useOrchestrator / useStreamingChat 接线 + 透传链

**Files:**
- Modify: `frontend/src/features/orchestrator/Composer.tsx`、`frontend/src/pages/Workspace.tsx`、`frontend/src/hooks/useOrchestrator.ts`、`frontend/src/hooks/useStreamingChat.ts`

**Interfaces:**
- Produces:完整透传链 `Workspace.onSend → useOrchestrator.send(text, engine, skillId) → useStreamingChat.send(...) → 请求体 skill_id`;Composer 插 `<SkillMenu/>`;Workspace 持 `skill` 状态 + 互斥规则。

- [ ] **Step 1: Implement**
- `useStreamingChat.ts` `send`(`:133-142`)加 `skillId: string | null = null` 参数,请求体(`:137`)加 `skill_id: skillId`:

```typescript
  const send = async (message: string, currentEngine: EngineType | null = null, skillId: string | null = null) => {
    ...
    streamChat({ session_id: sessionId, message, current_engine: currentEngine, skill_id: skillId }, signal);
```

- `useOrchestrator.ts` `send`(`:87-96`)加 `skillId: string | null = null`,透传 `chatRef.current.send(text, currentEngine, skillId)`。
- `Composer.tsx`:`OpenMenu`(`:69`)加 `| 'skill'`;props 加 `skills/skill/onSkillChange/onImportSkill`;在 mode chip(`:196-239`)与 `flex-1` spacer(`:241`)之间插 `<SkillMenu/>`(放在 `toolbarRef` 容器内,outside-click/Escape 零改动);`openMenu === 'skill'` 时传 `open`。
- `Workspace.tsx`:加 `const [skill, setSkill] = useState<SkillMeta | null>(null)`、`const [importOpen, setImportOpen] = useState(false)`;`handleSkillChange`:`setSkill(s); if (s) setRoute('auto')`;`handleRouteChange`(`:63-67`)末尾加 `if (route !== 'auto') setSkill(null)`;`onSend`(`:238`):`send(text, route === 'auto' ? null : route, skill?.name ?? null)`;把 `skills/skill/onSkillChange={handleSkillChange}/onImportSkill={() => setImportOpen(true)}/open={openMenu==='skill'}` 传给 Composer;渲染 `<SkillImportModal open={importOpen} onClose={...} onImported={(s) => { setSkill(s); setImportOpen(false); }} />`。

- [ ] **Step 2: Verify**

Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: PASS(全前端测试 + lint + 构建通过)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useStreamingChat.ts frontend/src/hooks/useOrchestrator.ts frontend/src/features/orchestrator/Composer.tsx frontend/src/pages/Workspace.tsx
git commit -m "feat(skills-fe): Composer/Workspace 接线 + 透传链 (skill_id → /chat/stream)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Phase 5: 契约 + 联调

### Task 5.1: demo 技能 + `api-contract-v2.md` 追加

**Files:**
- Create: `docs/demo-skills/capacity-report.md`(可导入的 demo 技能)
- Modify: `docs/api-contract-v2.md`(追加端点总览三行、§1 `skill_id` 字段、新小节「技能模块」)

**Interfaces:** 无(文档 + 夹具)。

- [ ] **Step 1: Create demo skill** (`docs/demo-skills/capacity-report.md`)

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

(可选第二 demo `dispatch-helper.md`,带 `allowed_tools: [check_kitting, dispatch_work_order]` + `tool_preconditions: {dispatch_work_order: [dispatch_ready]}`,用于 e2e 走查前置断言拦截路径——非必需,单元测试已覆盖。)

- [ ] **Step 2: Append to `docs/api-contract-v2.md`** (照 v1 §5):
1. 端点总览表加 `GET /skills` / `POST /skills/import`(201)/ `DELETE /skills/{name}` 三行。
2. §1:`/chat` 与 `/chat/stream` 请求体新增可选 `skill_id: str | null`;`route` 帧 `intent` 枚举加 `"skill"`、payload 加 `skill_id`(非技能为 null)。
3. 新小节「技能模块 (Skills)」:`SkillMeta` 形状(字段表)、multipart 约定(`file` 字段,.md/.zip)、错误语义(413/415/422/409)、frontmatter 规范链接 `docs/skills-design-v1.md` §2。

- [ ] **Step 3: Commit**

```bash
git add docs/demo-skills/capacity-report.md docs/api-contract-v2.md
git commit -m "docs(skills): demo capacity-report 技能 + api-contract-v2 追加 skills 端点

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 5.2: 端到端联调验收

**Files:** 无(手动走查)。

- [ ] **Step 1: 启动 + 导入**

```bash
./restart.sh   # 后端 :8000 + 前端 :5173
curl -F "file=@docs/demo-skills/capacity-report.md" :8000/skills/import   # 期望 201 + SkillMeta
curl :8000/skills                                                          # 期望含 capacity-report
```
Expected:导入返回 201;`GET /skills` 列出该技能。

- [ ] **Step 2: 前端选中 → 发送**

浏览器开 `:5173`;Composer「技能」chip → 选中「产能日报」(确认 route 自动回 auto);发送「给我出一份今天的产能报告」。
Expected:DevTools Network `/chat/stream` 请求体含 `skill_id: "capacity-report"`;SSE `route` 帧 `intent:"skill"`、`skill_id:"capacity-report"`;ReAct 执行(只读工具调用);回复为产能结论。

- [ ] **Step 3: 审计时间线**

```bash
curl :8000/audit/timeline | grep capacity-report
```
Expected:审计记录 `route` 事件 `result.skill_id == "capacity-report"`、`route_method == "forced"`。

- [ ] **Step 4: 删除 + 回归**

```bash
curl -X DELETE :8000/skills/capacity-report   # 期望 {"deleted": true, ...}
```
Expected:删除后前端列表刷新;再次调用同 skill_id 的会话回复「技能 capacity-report 不存在或已被删除」。

- [ ] **Step 5: Final commit (若有走查修复)**

```bash
git add -A && git commit -m "chore(skills): 端到端联调修复" || echo "无需修复"
```

---

## Self-Review

**1. Spec coverage**(v1/v2 → 任务):
- frontmatter 10 字段 + 校验规则 1-6 → Task 1.1 / 1.2(含 `tool_preconditions` key/断言名校验)✅
- zip 安全(穿越/符号链接/成员数/大小)+ SKILL.md 归一化 → Task 1.2 ✅
- SkillStore(catalog+落盘+version+路由数据供给+read_attachment 防穿越)→ Task 1.3 ✅
- `named_preconditions`(dispatch_ready/expedite_valid,普通 dict)+ `read_skill_file` 工具 → Task 2.1 ✅
- 3 端点(201/413/415/422/409)+ ChatRequest.skill_id → Task 2.2 ✅
- AgentLoop `extra_preconditions`(只叠加不替换,缺省 None 不变)→ Task 3.1 ✅
- SkillEngine(not-found/llm-unavailable/执行/断言拦截)+ `extra_preconditions` 装配 → Task 3.2 ✅
- RouteDecision skill intent + skill_id → Task 3.4 ✅
- EmbeddingRouter version 拉式失效 + 技能向量(分叉 A1)→ Task 3.5 ✅
- `_classify_system` 候选拼接(无技能逐字节一致)+ skill_id 校验降 ambiguous(分叉 B1)→ Task 3.6 ✅
- Orchestrator forced/dispatch/record + `_contract_route` + chat 透传 → Task 3.7 ✅
- 前端:类型 → Task 4.1;数据层 → 4.2;MSW → 4.3;Modal → 4.4;SkillMenu → 4.5;SkillImportModal → 4.6;ROUTE_META+UploadProgress → 4.7;接线透传 → 4.8 ✅
- 契约 + demo + e2e → Task 5.1 / 5.2 ✅
- 15 条 drift:Modal `bg-surface-1`(4.4)、`text-accent-fg`+leftBorder(4.7)、`useImportSkill`(4.2)、`UploadProgress.fillClassName`(4.6/4.7)、201(2.2)、`AuditLog`/`task`/路径(3.x)——均已落入对应任务 ✅

**2. Placeholder scan**:无 "TBD/TODO/适当处理";每步含实际代码与命令。`Precondition` 类型与 `_handle_call` 精确插入行已在 Task 3.1 给出(Task 3.0 阅读确认)。`Settings.react_max_steps` 字段名沿用 bootstrap 既有 AgentLoop 构造表达式;若实际名不同,在 Task 3.2 实现时对齐(已在 Task 3.2 备注提示)。

**3. Type consistency**:
- `SkillEngine.handle(skill_id, message, session_id, history, on_progress)` 在 Task 3.2(定义)、3.3(`_dispatch` 调用)、3.7(forced 分支经 `_dispatch`)一致 ✅
- `validate_allowed_tools(fm, registered, default, named)` 在 Task 1.2(定义)、2.2(端点调用,传 `set(tools.names())` / `QUERY_READONLY_TOOLS` / `set(named_preconditions.keys())`)签名一致 ✅
- `EmbeddingRouter(llm, examples, skills=)` 在 3.5(定义)、3.6(bootstrap 透传)、4.x(无前端引用)一致 ✅
- `IntentRouter(llm, settings, embed, skills=)` 在 3.6 定义与 bootstrap 一致 ✅
- `RouteDecision(intent="skill", skill_id=, confidence=, route_method="forced")` 在 3.4(字段)、3.6(embedding/LLM)、3.7(forced)一致 ✅
- 前端 `skill_id?: string | null` 在 4.1(类型)、4.8(useStreamingChat body)一致 ✅

无遗漏;计划可执行。

---

## Execution Handoff

Plan complete and saved to `docs/skills-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 我为每个任务派发一个全新 subagent,任务间做两阶段评审(green-test 评审 + 设计评审),快速迭代;我持上下文把关一致性。

**2. Inline Execution** — 在本会话内用 executing-plans 批量执行,带检查点评审。

**Which approach?**

(若选 Subagent-Driven,启用 superpowers:subagent-driven-development;若选 Inline,启用 superpowers:executing-plans。)

