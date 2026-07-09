"""工具观察离线暂存 (方案2)。

超过回喂上限的工具观察不再有损截断，而是整对象存入本 store，上下文/轨迹里只放一个
**紧凑句柄** (observation_ref + 规模 + 字段名 + 少量预览)。模型可用 read_observation 工具
分页取回，前端可经 GET /observations/{ref} 懒加载。

进程内存储 (FIFO 上限淘汰)，与本仓库 pending/context 的 process-transient 约定一致：重启后
旧 ref 失效。单用户场景下 ref 全局唯一自增即可，无需按会话命名空间。
"""

import json
from collections import OrderedDict
from typing import Any

# 句柄自身与分页返回都必须有界。子预算用于句柄内的 preview，留足余量给 ref/规模等元数据。
_PREVIEW_ITEMS = 3  # list 句柄预览的条数
_PREVIEW_VALUE_CHARS = 200  # dict 预览/单值预览的字符上限
_MAX_LIMIT = 100  # get 单页条数硬上限


def _bytes(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def _clip_str(s: str, n: int = _PREVIEW_VALUE_CHARS) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _preview_value(value: Any) -> Any:
    """把单个值压成预览: 长字符串截断，容器只留规模摘要，标量原样。"""
    if isinstance(value, str):
        return _clip_str(value)
    if isinstance(value, list):
        return f"<list len={len(value)}>"
    if isinstance(value, dict):
        return f"<dict keys={list(value)[:8]}>"
    return value


class ObservationStore:
    """观察离线暂存 + 分页读取。"""

    def __init__(self, cap: int = 200):
        self._cap = cap
        self._store: "OrderedDict[str, Any]" = OrderedDict()
        self._counter = 0

    def put(self, observation: Any) -> dict:
        """存全量对象，返回紧凑句柄 (自身有界)。"""
        self._counter += 1
        ref = f"obs-{self._counter}"
        self._store[ref] = observation
        while len(self._store) > self._cap:  # FIFO 淘汰最旧
            self._store.popitem(last=False)

        handle: dict = {
            "observation_ref": ref,
            "original_bytes": _bytes(observation),
            "hint": (
                f'结果过大已离线暂存。用 read_observation(ref="{ref}", offset, limit) '
                "分页查看，或用更精确的参数(状态/ids)缩小范围。不要臆造未取回的内容。"
            ),
        }
        if isinstance(observation, list):
            handle["kind"] = "list"
            handle["total"] = len(observation)
            first = observation[0] if observation else None
            handle["item_keys"] = list(first) if isinstance(first, dict) else None
            handle["preview"] = [
                {k: _preview_value(v) for k, v in item.items()}
                if isinstance(item, dict) else _preview_value(item)
                for item in observation[:_PREVIEW_ITEMS]
            ]
        elif isinstance(observation, dict):
            handle["kind"] = "dict"
            handle["total"] = len(observation)
            handle["item_keys"] = list(observation)
            handle["preview"] = {k: _preview_value(v) for k, v in observation.items()}
        else:
            handle["kind"] = "scalar"
            text = observation if isinstance(observation, str) else json.dumps(
                observation, ensure_ascii=False, default=str
            )
            handle["total"] = len(text)
            handle["preview"] = _clip_str(text)
        return handle

    def get(
        self,
        ref: str,
        offset: int = 0,
        limit: int = 20,
        keys: list[str] | None = None,
    ) -> dict:
        """分页取回。缺失 ref 返回 error (不抛异常，便于回喂模型 / HTTP 404 判定)。"""
        if ref not in self._store:
            return {"error": f"观察 {ref} 不存在或已过期"}
        value = self._store[ref]
        offset = max(0, offset)
        limit = max(1, min(limit, _MAX_LIMIT))

        if isinstance(value, list):
            page = [self._cap_item(x) for x in value[offset : offset + limit]]
            return {
                "observation_ref": ref, "kind": "list", "total": len(value),
                "offset": offset, "limit": limit, "items": page,
                "has_more": offset + limit < len(value),
            }
        if isinstance(value, dict):
            if keys is not None:
                subset = {k: value[k] for k in keys if k in value}
                return {"observation_ref": ref, "kind": "dict", "keys": subset}
            return {  # 未指定 keys → 顶层键 + 值预览 (可据此再按 keys 深入)
                "observation_ref": ref, "kind": "dict", "total": len(value),
                "item_keys": list(value),
                "preview": {k: _preview_value(v) for k, v in value.items()},
            }
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        return {
            "observation_ref": ref, "kind": "scalar", "total": len(text),
            "offset": offset, "limit": limit, "slice": text[offset : offset + limit],
            "has_more": offset + limit < len(text),
        }

    @staticmethod
    def _cap_item(item: Any) -> Any:
        """单条元素若本身超大 → 压成预览，避免整页回喂再次触发离线 (防递归)。"""
        if _bytes(item) <= 4096:
            return item
        if isinstance(item, dict):
            return {k: _preview_value(v) for k, v in item.items()}
        return _preview_value(item)
