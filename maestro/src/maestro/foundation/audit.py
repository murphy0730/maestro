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
    def __init__(self, file_path: Path | None = None, rehydrate_max: int = 2000):
        self._entries: list[AuditEntry] = []
        self._file_path = file_path
        if file_path is not None:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._entries = self._rehydrate(file_path, rehydrate_max)

    @staticmethod
    def _rehydrate(file_path: Path, max_lines: int) -> list[AuditEntry]:
        """启动时回灌 jsonl 尾部，使 /audit 查询跨重启可追溯 (内存为主、文件为源)。

        只取尾部 max_lines 行 (文件长期增长，反向按块读避免全量加载)；坏行跳过。"""
        if max_lines <= 0 or not file_path.exists():
            return []
        try:
            with file_path.open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                data = b""
                while size > 0 and data.count(b"\n") <= max_lines:
                    step = min(65536, size)
                    size -= step
                    f.seek(size)
                    data = f.read(step) + data
        except OSError as e:
            logger.warning("审计日志回灌读取失败，从空历史启动: %s", e)
            return []
        entries: list[AuditEntry] = []
        for line in data.splitlines()[-max_lines:]:
            if not line.strip():
                continue
            try:
                entries.append(AuditEntry.model_validate_json(line))
            except Exception as e:  # noqa: BLE001 — 单行损坏不拖垮回灌
                logger.warning("审计日志存在损坏行，已跳过: %s", e)
        return entries

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

    def query(
        self,
        action: str | None = None,
        limit: int = 100,
        actor_in: set[str] | None = None,
    ) -> list[AuditEntry]:
        entries = self._entries
        if action:
            entries = [e for e in entries if action in e.action]
        if actor_in is not None:
            # 在截断 limit 之前过滤，避免目标 actor 的旧条目被系统噪音挤出窗口
            entries = [e for e in entries if e.actor in actor_in]
        return entries[-limit:]
