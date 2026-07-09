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

# 写动作授权策略配置表 (action_type → 级别)，未知写动作默认需确认 (保守)。
DEFAULT_POLICIES: dict[str, ActionLevel] = {
    "send_expedite_message.internal": "auto",
    "send_expedite_message.supplier": "requires_confirmation",
    "dispatch_work_order": "requires_confirmation",
    "update_work_order_status": "requires_confirmation",
    "send_notification": "requires_confirmation",
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
        """评估一次工具调用 (读/写/中性统一)。默认 allow, 规则可覆盖为 deny/ask。"""
        for rule in self._rules:
            if rule.matches_tool(name, kind):
                return PermissionDecision(rule.effect, rule.reason or f"规则匹配工具 {name}", "rule")
        return PermissionDecision("allow", source="default")

    def evaluate_action(self, action_type: str) -> PermissionDecision:
        """评估一个写动作 (ActionGate 决策来源)。规则优先, 否则查策略表, 未知则 ask。"""
        for rule in self._rules:
            if rule.matches_action(action_type):
                return PermissionDecision(rule.effect, rule.reason, "rule")
        level = self._action_policies.get(action_type)
        if level is None:
            return PermissionDecision("ask", "未知写动作默认需确认", "policy-default")
        return PermissionDecision(_LEGACY_TO_EFFECT[level], source="policy")


def effect_to_level(effect: PermissionEffect) -> ActionLevel:
    return _EFFECT_TO_LEGACY[effect]
