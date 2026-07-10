"""平台配置 (pydantic-settings + .env)。

所有 LLM 配置 (base_url / api_key / model) 走环境变量，不在代码中硬编码。
"""

import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def project_root() -> Path:
    """项目根目录。打包冻结后 (PyInstaller) 返回 sys._MEIPASS，使种子数据
    (data/mock、随包 yaml) 路径解析到冻结包内已收录的位置。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def _runtime_data_root() -> Path:
    """运行时可写数据根目录。打包后由 Electron 经 MAESTRO_DATA_DIR 注入 (userData)；
    未设置时回退到 ~/.maestro (与项目目录解耦，重装/重新 clone 不丢数据)。
    种子数据 (mock/knowledge) 不走此处。"""
    env = os.environ.get("MAESTRO_DATA_DIR")
    return Path(env) if env else Path.home() / ".maestro"


def runtime_data_root() -> Path:
    """对外公开的可写数据根目录 (默认 ~/.maestro，可被 MAESTRO_DATA_DIR 覆盖)。

    供 model_config 等模块读写 settings.json，避免在多处重复 _runtime_data_root 实现。
    """
    return _runtime_data_root()


class MCPServerSettings(BaseModel):
    """A serialisable MCP server definition stored in settings.json or .env."""

    name: str
    transport_type: Literal["stdio", "sse", "websocket", "http"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """优先级: 显式环境变量 (含 Electron 注入的 LLM_*/EMBED_*) > <数据根>/settings.json
        > .env > 字段默认值。settings.json 让 CLI/dev 把模型连接信息与 .env 解耦,
        路径随 _runtime_data_root() (默认 ~/.maestro),缺失时该源返回空、不报错。"""
        json_source = JsonConfigSettingsSource(
            settings_cls, json_file=_runtime_data_root() / "settings.json"
        )
        return (init_settings, env_settings, json_source, dotenv_settings, file_secret_settings)

    # LLM (OpenAI 兼容接口)。api_key 只从环境变量 / .env 读取，绝不写在代码里。
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"

    # Embedding (OpenAI 兼容 /embeddings；用于意图路由第 1 层语义路由)
    # embed_model 留空 → 嵌入路由禁用，路由直接走 LLM 分类层。
    # embed_base_url / embed_api_key 留空时回退复用上面的 LLM 配置。
    embed_model: str = ""
    embed_base_url: str = ""
    embed_api_key: str = ""

    # 多供应商模型配置 (前端设置弹框通过 PUT /models 写入 <数据根>/settings.json 的
    # `model_providers` 键)。形如 {"llm": {"providers": [...], "active_id": ...},
    # "embedding": {...}}。若某 section 存在 active provider，其 base_url/api_key/model
    # 会覆盖上面的扁平默认值 (see maestro.foundation.model_config / bootstrap)。
    model_providers: dict | None = None

    # MCP servers are connected during FastAPI lifespan startup.  Empty is a
    # safe default and keeps CLI/tests free of external processes.
    mcp_servers: list[MCPServerSettings] = Field(default_factory=list)

    # 路由 / 策略选择 置信度门控
    route_confidence_threshold: float = 0.8
    embed_confidence_threshold: float = 0.72  # 嵌入路由：top 相似度 ≥ 此值才直接路由
    strategy_confidence_threshold: float = 0.7

    # 调度引擎 (ReAct 智能体) 护栏
    react_max_steps: int = 8  # 思考-行动循环最大步数 (防无限循环/绕路)
    react_observation_max_bytes: int = 8192  # 单条工具观察回喂上限，超出离线暂存 (防上下文爆炸)
    react_observation_store_max: int = 200  # 观察离线暂存的全局条数上限 (FIFO 淘汰)

    # 技能引擎护栏
    skill_body_max_bytes: int = 128 * 1024  # 单个技能包 SKILL.md 正文字节上限 (导入校验)
    skill_prompt_max_bytes: int = 256 * 1024  # 多技能合并后渲染进 system prompt 的总字节上限
    skill_max_depth: int = 2  # invoke_skill 嵌套深度上限 (防无界递归)

    # 查询引擎 (RAG)
    rag_top_k: int = 3  # 每次检索返回的知识片段数
    # 向量库后端: "chroma" (PersistentClient 持久化) | "memory" (进程内, 测试/降级用)
    vector_backend: str = "chroma"

    # 事件层
    patrol_interval_seconds: float = 30.0
    kitting_lookahead_days: int = 3

    # 数据与日志
    # mock_data_dir / knowledge_dir 为种子数据，随包发布 (只读)，不走 userData。
    mock_data_dir: Path = Field(default_factory=lambda: project_root() / "data" / "mock")
    knowledge_dir: Path = Field(
        default_factory=lambda: project_root() / "data" / "mock" / "knowledge"
    )
    # 用户上传的知识文档落盘目录 (运行时数据，与种子知识库分开，不入 git)
    knowledge_upload_dir: Path = Field(
        default_factory=lambda: _runtime_data_root() / "knowledge_uploads"
    )
    audit_log_file: Path | None = Field(
        default_factory=lambda: _runtime_data_root() / "logs" / "audit.jsonl"
    )
    sessions_dir: Path = Field(
        default_factory=lambda: _runtime_data_root() / "sessions"
    )
    # 技能包落盘目录 (SkillStore 索引 + 各技能包 SKILL.md 与附属文件，运行时数据，不入 git)
    skills_dir: Path = Field(default_factory=lambda: _runtime_data_root() / "skills")
    # Chroma 向量库持久化目录 (vector_backend=chroma 时使用，运行时数据，不入 git)
    chroma_dir: Path = Field(default_factory=lambda: _runtime_data_root() / "chroma")
