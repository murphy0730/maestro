from dataclasses import asdict, dataclass
from enum import Enum
from typing import Literal


class ExecutionMode(str, Enum):
    SANDBOXED = "sandboxed"
    GUARDED = "guarded"


@dataclass(frozen=True)
class SecurityCapabilities:
    execution_mode: ExecutionMode
    os_sandbox: bool
    filesystem_isolation: Literal["srt", "account_acl_only", "none"]
    network_isolation: Literal["srt", "firewall", "proxy", "none"]
    process_tree_control: bool
    command_inspection: bool = True

    def to_dict(self) -> dict:
        value = asdict(self)
        value["execution_mode"] = self.execution_mode.value
        return value


@dataclass(frozen=True)
class CommandRisk:
    effect: Literal["allow", "ask", "deny"]
    categories: list[str]
    reason: str
    commands: list[str]
    matched_rules: list[str]
    parse_complete: bool = True

    def to_dict(self) -> dict:
        return asdict(self)
