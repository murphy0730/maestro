"""平台配置 (pydantic-settings + .env)。

所有 LLM 配置 (base_url / api_key / model) 走环境变量，不在代码中硬编码。
"""

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """返回项目根目录 (scheduling_platform/，即 src 的上一级)。"""
    return Path(__file__).resolve().parents[2]


def _runtime_data_root() -> Path:
    """运行时可写数据根目录。打包后由 Electron 经 MAESTRO_DATA_DIR 注入 (userData)；
    未设置时回退到项目内 data/ (CLI/dev 不变)。种子数据 (mock/knowledge) 不走此处。"""
    env = os.environ.get("MAESTRO_DATA_DIR")
    return Path(env) if env else project_root() / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

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

    # 路由 / 策略选择 置信度门控
    route_confidence_threshold: float = 0.8
    embed_confidence_threshold: float = 0.72  # 嵌入路由：top 相似度 ≥ 此值才直接路由
    strategy_confidence_threshold: float = 0.7

    # 调度引擎 (ReAct 智能体) 护栏
    react_max_steps: int = 8  # 思考-行动循环最大步数 (防无限循环/绕路)
    react_observation_max_bytes: int = 8192  # 单条工具观察回喂上限，超出截断 (防上下文爆炸)

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
