"""统一权限规则引擎 (对齐 Claude Code 的 checkPermissions)。

从 ActionGate 抽出的独立决策层: 对读/写/中性工具与写动作统一评估，输出三态
allow / deny / ask，替代原先散落在 AuthZ 内的硬编码判级。

- allow: 放行执行。
- deny:  拒绝执行。
- ask:   需人确认 —— 写动作 → ActionGate 生成 PendingAction; 读/中性工具 → ReAct
         的 can_use_tool 交互确认层挂起。

规则集中声明、可外部注入 (rules / action_policies)，提升可配置性与可审计性。
ActionGate 仍是写操作的具体执行闸门，但其 AuthZ.decide 的决策来源改为调用本引擎。
"""

from dataclasses import dataclass
from typing import Literal

from maestro.foundation.exec_context import ExecMode

# 写动作分级 (ActionGate 语义) 与本引擎三态的双向映射
ActionLevel = Literal["auto", "requires_confirmation", "deny"]
PermissionEffect = Literal["allow", "deny", "ask"]

_LEGACY_TO_EFFECT: dict[ActionLevel, PermissionEffect] = {
    "auto": "allow",
    "requires_confirmation": "ask",
    "deny": "deny",
}
_EFFECT_TO_LEGACY: dict[PermissionEffect, ActionLevel] = {
    "allow": "auto",
    "ask": "requires_confirmation",
    "deny": "deny",
}

# 写生产系统的动作: 无论何种执行模式都必须人工确认。
# 完全访问模式 (auto) 只放开文件/网络等非生产写入，绝不放开这些。
# 注入规则可以把它们收紧为 deny，但不能降级为 allow。
PRODUCTION_WRITE_ACTIONS: frozenset[str] = frozenset(
    {
        "dispatch_work_order",
        "update_work_order_status",
        "send_notification",
        "send_expedite_message.supplier",
        "send_expedite_message.internal",
        "record_followup",
    }
)

# 写动作授权策略配置表 (action_type → 级别)，未知写动作默认需确认 (保守)。
# 生产写入已由 PRODUCTION_WRITE_ACTIONS 无条件兜底，此表供外部注入非生产动作用。
DEFAULT_POLICIES: dict[str, ActionLevel] = {
    # 即使 Skill 包 hash 已被信任，每一次脚本执行仍需经过 ActionGate。
    "run_skill_script": "requires_confirmation",
}


@dataclass
class PermissionDecision:
    effect: PermissionEffect
    reason: str = ""
    source: str = "default"  # rule / policy / default —— 便于审计决策来源


@dataclass
class PermissionRule:
    """一条权限规则。匹配到即生效 (先匹配者优先)。

    - 工具规则: 指定 tool (工具名) 和/或 kind (read/write/aux)。
    - 写动作规则: 指定 action_type (如 send_expedite_message.supplier)。
    """

    effect: PermissionEffect
    tool: str | None = None
    kind: str | None = None
    action_type: str | None = None
    reason: str = ""

    def matches_tool(self, name: str, kind: str) -> bool:
        if self.action_type is not None:
            return False
        if self.tool is None and self.kind is None:
            return False  # 空规则不匹配任何工具, 避免误伤
        if self.tool is not None and self.tool != name:
            return False
        if self.kind is not None and self.kind != kind:
            return False
        return True

    def matches_action(self, action_type: str) -> bool:
        return self.action_type is not None and self.action_type == action_type


class PermissionEngine:
    """规则化权限评估。工具与写动作共用一套规则集。"""

    def __init__(
        self,
        rules: list[PermissionRule] | None = None,
        action_policies: dict[str, ActionLevel] | None = None,
    ):
        self._rules: list[PermissionRule] = list(rules or [])
        self._action_policies = {**DEFAULT_POLICIES, **(action_policies or {})}

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)

    def evaluate_tool(self, name: str, kind: str, arguments: dict | None = None) -> PermissionDecision:
        """评估工具调用。多个规则命中时采用 deny > ask > allow。"""
        matches = [rule for rule in self._rules if rule.matches_tool(name, kind)]
        if matches:
            rule = min(matches, key=lambda item: {"deny": 0, "ask": 1, "allow": 2}[item.effect])
            return PermissionDecision(rule.effect, rule.reason or f"规则匹配工具 {name}", "rule")
        return PermissionDecision("allow", source="default")

    def evaluate_action(
        self, action_type: str, mode: ExecMode = "plan"
    ) -> PermissionDecision:
        """评估一个写动作 (ActionGate 决策来源)。

        顺序:
        1. deny 规则 —— 收紧永远允许，即便对生产写入
        2. 生产系统写入 → ask (任何模式，规则不能降级)
        3. 其余匹配规则 → 该规则的 effect
        4. 策略表命中 → 该策略的 effect
        5. mode == "auto" → allow (完全访问模式放开文件/网络等非生产写入)
        6. → ask (未知写动作保守)
        """
        matches = [rule for rule in self._rules if rule.matches_action(action_type)]
        deny = next((rule for rule in matches if rule.effect == "deny"), None)
        if deny is not None:
            return PermissionDecision("deny", deny.reason, "rule")
        if action_type in PRODUCTION_WRITE_ACTIONS:
            return PermissionDecision("ask", "写生产系统，任何模式都需人工确认", "production")
        rule = next((rule for effect in ("ask", "allow") for rule in matches if rule.effect == effect), None)
        if rule is not None:
            return PermissionDecision(rule.effect, rule.reason, "rule")
        level = self._action_policies.get(action_type)
        if level is not None:
            return PermissionDecision(_LEGACY_TO_EFFECT[level], source="policy")
        if mode == "auto":
            return PermissionDecision("allow", "完全访问模式: 非生产写入放行", "mode")
        return PermissionDecision("ask", "默认模式: 写操作需人工确认", "mode")


def effect_to_level(effect: PermissionEffect) -> ActionLevel:
    return _EFFECT_TO_LEGACY[effect]
