"""模型供应商配置在 settings.json 上的读写与解析。

- 写入: 前端设置弹框保存模型时，PUT /models 把完整 providers 结构落到
  <数据根>/settings.json 的 `model_providers` 键 (原子写)。
- 读取: 后端启动时 (bootstrap) 与运行时热更新 (/admin/reload-model) 都从这里解析
  **active provider**，用它覆盖 config 的扁平 LLM_* 默认值，使后端真正使用用户启用的模型。

与 .env / 环境变量的关系: settings.json 的 model_providers 只是 LLM 连接的"用户态"来源，
环境变量 (含 Electron 注入) 优先级更高 (见 config.Settings.settings_customise_sources)。
"""

import json
import logging
from pathlib import Path
from typing import Any

from maestro.config import runtime_data_root
from maestro.foundation.settings_json_store import SettingsJsonStore

logger = logging.getLogger(__name__)

MODELS_KEY = "model_providers"

EMPTY_PROVIDERS: dict[str, Any] = {
    "llm": {"providers": [], "active_id": None},
    "embedding": {"providers": [], "active_id": None},
}


def settings_json_path() -> Path:
    return runtime_data_root() / "settings.json"


def load_model_providers() -> dict | None:
    """读取 settings.json 的 `model_providers` 块; 文件缺失/损坏返回 None。"""
    p = settings_json_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("读取 settings.json 失败，忽略模型配置: %s", e)
        return None
    return data.get(MODELS_KEY)


def save_model_providers(cfg: dict) -> None:
    """原子写: 把 providers 结构落到 settings.json 的 `model_providers` 键，
    保留文件中其它既有键 (如可能由 .env 预置的扁平键)。"""
    p = settings_json_path()
    SettingsJsonStore(p).update_section(MODELS_KEY, cfg)
    logger.info("已写入模型配置到 %s", p)


def merge_preserving_secrets(new_cfg: dict, old_cfg: dict | None) -> dict:
    """PUT 载荷里 api_key 为空的 provider，若旧配置存在同 id 条目则保留旧 key。

    GET /models 出于安全脱敏 api_key；前端"回读-保存"的载荷因此带空 key，
    不做保留合并会把已存密钥清空。显式提供非空 key 时照常覆盖。"""
    if not old_cfg:
        return new_cfg
    for section in ("llm", "embedding"):
        old_by_id = {
            p.get("id"): p
            for p in (old_cfg.get(section) or {}).get("providers") or []
            if p.get("id")
        }
        for p in (new_cfg.get(section) or {}).get("providers") or []:
            if not p.get("api_key") and p.get("id") in old_by_id:
                p["api_key"] = old_by_id[p["id"]].get("api_key", "")
    return new_cfg


def redact_providers(cfg: dict | None) -> dict:
    """对外响应脱敏: api_key 一律置空，另给 api_key_set 派生标记。"""
    src = cfg if cfg is not None else EMPTY_PROVIDERS
    out: dict[str, Any] = {}
    for section in ("llm", "embedding"):
        sec = src.get(section) or {}
        out[section] = {
            "providers": [
                {**p, "api_key": "", "api_key_set": bool(p.get("api_key"))}
                for p in sec.get("providers") or []
            ],
            "active_id": sec.get("active_id"),
        }
    return out


def active_provider(providers: dict | None, section: str) -> dict | None:
    """从 providers 块取某 section 的 active provider (按 active_id 匹配)。"""
    if not providers:
        return None
    sec = providers.get(section) or {}
    provs = sec.get("providers") or []
    active_id = sec.get("active_id")
    if active_id is None:
        return None
    for p in provs:
        if p.get("id") == active_id:
            return p
    return None


def resolve_from_providers(providers: dict | None, fallback: Any) -> tuple[str, str, str, str, str, str]:
    """解析生效的 (base_url, api_key, model, embed_base, embed_key, embed_model)。

    providers 为 settings.json 的 model_providers 块; fallback 为任意带
    llm_base_url/llm_api_key/llm_model/embed_* 属性的对象 (如 Settings / Platform.settings)，
    在对应 section 无 active provider 时回退到扁平默认值。
    """
    llm_p = active_provider(providers, "llm")
    embed_p = active_provider(providers, "embedding")

    def fb(name: str, default: str = "") -> str:
        return getattr(fallback, name, default)

    base = (llm_p or {}).get("base_url") or fb("llm_base_url")
    key = (llm_p or {}).get("api_key") or fb("llm_api_key")
    model = (llm_p or {}).get("model") or fb("llm_model")
    embed_base = (embed_p or {}).get("base_url") or fb("embed_base_url") or base
    embed_key = (embed_p or {}).get("api_key") or fb("embed_api_key") or key
    embed_model = (embed_p or {}).get("model") or fb("embed_model")
    return (base, key, model, embed_base, embed_key, embed_model)
