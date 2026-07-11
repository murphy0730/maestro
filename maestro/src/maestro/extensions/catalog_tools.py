"""扩展目录 (SkillHub / 连接器市场) 工具。

让调度 ReAct 智能体与查询引擎能搜索技能目录、安装技能、添加 MCP 连接器——
补上“查找/安装技能”这一能力缺口，避免 Agent 退化成编造 CLI 命令的话术。

- search_catalog_skills / search_catalog_connectors: 只读，自由调用。
- install_catalog_skill / add_catalog_connector: 写操作，经 ActionGate 判级
  (默认 plan 模式需人工确认；auto 模式放行)。安装/添加前先查目录项 installable，
  不可安装立即返回原因，不进入确认流。

catalog_service 在 bootstrap 中延迟绑定 platform (构造时 platform 可为 None)，
仅在各方法的运行期调用时才需要 platform，故工具闭包捕获 service 即可。
"""

from __future__ import annotations

import json
import logging

from maestro.domain.models import ActionResult
from maestro.foundation.authz import ActionGate, gate_outcome_summary
from maestro.foundation.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _skill_summary(item: object) -> dict:
    return {
        "catalog_id": item.catalog_id,
        "name": item.name,
        "display_name": item.display_name,
        "description": item.description,
        "source": item.source_id,
        "license": item.license,
        "version": item.version,
        "compatibility_status": item.compatibility_status,
        "installable": item.installable,
        "install_block_reason": item.install_block_reason,
        "installed": item.installed,
        "update_available": item.update_available,
        "has_scripts": item.has_scripts,
    }


def _connector_summary(item: object) -> dict:
    return {
        "catalog_id": item.catalog_id,
        "name": item.name,
        "display_name": item.display_name,
        "description": item.description,
        "source": item.source_id,
        "version": item.version,
        "command": item.command,
        "args": item.args,
        "requirements": item.requirements,
        "required_env": [spec.name for spec in item.env_schema if spec.required],
        "secret_env": [spec.name for spec in item.env_schema if spec.secret],
        "installable": item.installable,
        "install_block_reason": item.install_block_reason,
        "configured": item.configured,
        "update_available": item.update_available,
    }


def _gate_outcome_dict(outcome) -> dict:
    result: dict = {"status": outcome.status, "summary": gate_outcome_summary(outcome)}
    if outcome.action is not None:
        result["action_id"] = outcome.action.action_id
    if outcome.result is not None:
        result["result"] = outcome.result.model_dump()
    return result


def register_catalog_tools(registry: ToolRegistry, catalog_service, gate: ActionGate) -> None:
    """把 4 个扩展目录工具注册进 foundation 共享 ToolRegistry。

    须在调度/查询引擎构造前调用，使其进入 scheduling_tools() 全集与
    QUERY_READONLY_TOOLS 只读集合。
    """

    async def search_catalog_skills(query: str = "", source: str = "") -> dict:
        """搜索技能目录 (SkillHub)。按关键词匹配 name/描述/作者/来源，可按来源过滤。"""
        items = catalog_service.list_skills(q=query, source_id=source or None)
        return {"total": len(items), "items": [_skill_summary(i) for i in items[:30]]}

    async def search_catalog_connectors(query: str = "", source: str = "") -> dict:
        """搜索连接器市场 (MCP)。按关键词匹配，可按来源过滤。"""
        items = catalog_service.list_connectors(q=query, source_id=source or None)
        return {"total": len(items), "items": [_connector_summary(i) for i in items[:30]]}

    async def install_catalog_skill(catalog_id: str) -> dict:
        """从目录安装一个技能到本地 SkillHub。不可安装(许可证/兼容性/已撤回)直接返回原因。"""
        item = catalog_service.store.skills.get(catalog_id)
        if item is None:
            return {"blocked": f"目录中不存在技能 {catalog_id}"}
        if not item.installable or item.withdrawn:
            return {"blocked": f"技能不可安装: {item.install_block_reason or '已撤回'}"}

        async def _execute() -> ActionResult:
            meta = await catalog_service.install_skill(catalog_id)
            return ActionResult(
                success=True,
                action="install_catalog_skill",
                detail=json.dumps(
                    {"name": meta.name, "package_sha256": meta.package_sha256},
                    ensure_ascii=False,
                ),
                ref_id=meta.name,
            )

        outcome = await gate.request(
            "install_catalog_skill",
            description=f"安装技能 {item.display_name} ({catalog_id})",
            params={"catalog_id": catalog_id},
            executor=_execute,
        )
        return _gate_outcome_dict(outcome)

    async def add_catalog_connector(
        catalog_id: str,
        name: str = "",
        display_name: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        expected_revision: int | None = None,
    ) -> dict:
        """从连接器市场添加一个 MCP 连接器(默认 enabled=false，不自动连接)。不可添加直接返回原因。"""
        item = catalog_service.store.connectors.get(catalog_id)
        if item is None:
            return {"blocked": f"目录中不存在连接器 {catalog_id}"}
        if not item.installable or item.withdrawn:
            return {"blocked": f"连接器不可添加: {item.install_block_reason or '已撤回'}"}

        payload = {
            "name": name or None,
            "display_name": display_name or None,
            "args": args,
            "env": env or {},
            "expected_revision": expected_revision,
        }

        async def _execute() -> ActionResult:
            server, revision = catalog_service.add_connector(catalog_id, payload)
            return ActionResult(
                success=True,
                action="add_catalog_connector",
                detail=json.dumps(
                    {"name": server.name, "revision": revision, "enabled": server.enabled},
                    ensure_ascii=False,
                ),
                ref_id=server.name,
            )

        outcome = await gate.request(
            "add_catalog_connector",
            description=f"添加连接器 {item.display_name} ({catalog_id})",
            params={"catalog_id": catalog_id, "name": payload["name"] or item.name},
            executor=_execute,
        )
        return _gate_outcome_dict(outcome)

    registry.register(
        "search_catalog_skills",
        "搜索技能目录(SkillHub): 按关键词查 name/描述/作者/来源，可按来源过滤。"
        "用于查找可安装的技能(如 word/docx/pdf/xlsx/pptx 等)。返回 installable/兼容性/许可证/是否已安装。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "关键词(留空返回全部)，如 word、docx、pdf"},
                "source": {
                    "type": "string",
                    "description": "来源过滤: openai-skills-curated / anthropics-skills",
                },
            },
        },
        search_catalog_skills,
        kind="read",
    )
    registry.register(
        "search_catalog_connectors",
        "搜索连接器市场(MCP): 按关键词查可添加的 MCP 连接器(filesystem/github/playwright/time 等)，可按来源过滤。"
        "返回 command/args/所需 Secret 名/是否已配置。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "关键词(留空返回全部)"},
                "source": {"type": "string", "description": "来源过滤"},
            },
        },
        search_catalog_connectors,
        kind="read",
    )
    registry.register(
        "install_catalog_skill",
        "从技能目录安装一个技能到本地 SkillHub(写操作，需确认)。先确认 installable=true。"
        "安装含脚本的技能后仍需单独信任才能执行脚本。",
        {
            "type": "object",
            "properties": {
                "catalog_id": {
                    "type": "string",
                    "description": "目录项 ID，形如 source_id:skill_name (从 search_catalog_skills 获得)",
                }
            },
            "required": ["catalog_id"],
        },
        install_catalog_skill,
        kind="write",
    )
    registry.register(
        "add_catalog_connector",
        "从连接器市场添加一个 MCP 连接器(写操作，需确认)。默认 enabled=false，不自动连接；"
        "需另行填写必要 Secret/路径后手动连接。",
        {
            "type": "object",
            "properties": {
                "catalog_id": {
                    "type": "string",
                    "description": "目录项 ID，形如 source_id:connector_name (从 search_catalog_connectors 获得)",
                },
                "name": {"type": "string", "description": "本地连接器名(留空用目录名)"},
                "display_name": {"type": "string"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "覆盖启动参数(留空用模板)",
                },
                "env": {
                    "type": "object",
                    "description": "环境变量(非 Secret 的普通值)",
                    "additionalProperties": {"type": "string"},
                },
                "expected_revision": {"type": "integer"},
            },
            "required": ["catalog_id"],
        },
        add_catalog_connector,
        kind="write",
    )
