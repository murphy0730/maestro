"""审计日志。

记录 (时间, actor, 动作类型, 参数, 授权结果, 执行结果)。
初始版本: 内存列表 + 结构化 jsonl 文件，可查询。
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    actor: str
    action: str
    params: dict = Field(default_factory=dict)
    authz_decision: str | None = None
    result: dict | None = None


class AuditLog:
    def __init__(self, file_path: Path | None = None):
        self._entries: list[AuditEntry] = []
        self._file_path = file_path
        if file_path is not None:
            file_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        actor: str,
        action: str,
        params: dict | None = None,
        authz_decision: str | None = None,
        result: dict | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            actor=actor,
            action=action,
            params=params or {},
            authz_decision=authz_decision,
            result=result,
        )
        self._entries.append(entry)
        logger.info("[AUDIT] %s %s decision=%s", actor, action, authz_decision)
        if self._file_path is not None:
            # 审计落盘是旁路: 写文件失败(IO 或脏数据序列化失败)只告警，
            # 绝不抛出拖垮主流程; 内存记录已在上面完成。
            try:
                line = entry.model_dump_json()
            except Exception as e:  # noqa: BLE001 — 含代理字符等脏数据
                logger.warning("审计日志序列化失败，跳过落盘: %s", e)
                return entry
            try:
                with self._file_path.open("a", encoding="utf-8", errors="replace") as f:
                    f.write(line + "\n")
            except OSError as e:
                logger.warning("审计日志写文件失败: %s", e)
        return entry

    def query(self, action: str | None = None, limit: int = 100) -> list[AuditEntry]:
        entries = self._entries
        if action:
            entries = [e for e in entries if action in e.action]
        return entries[-limit:]
