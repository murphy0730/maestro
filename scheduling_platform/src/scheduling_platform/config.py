"""平台配置 (pydantic-settings + .env)。

所有 LLM 配置 (base_url / api_key / model) 走环境变量，不在代码中硬编码。
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """返回项目根目录 (scheduling_platform/，即 src 的上一级)。"""
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (OpenAI 兼容接口)
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = "sk-94d59c4101b14b7fad6c4ffce5ba9f76"
    llm_model: str = "deepseek-v4-pro"

    # Embedding (OpenAI 兼容 /embeddings；用于意图路由第 1 层语义路由)
    # embed_model 留空 → 嵌入路由禁用，路由直接走 LLM 分类层。
    # embed_base_url / embed_api_key 留空时回退复用上面的 LLM 配置。
    embed_model: str = "BAAI/bge-m3"
    embed_base_url: str = "https://api.siliconflow.cn/v1/embeddings"
    embed_api_key: str = "sk-pmwnayqycewmwxnksnzhjhshonpxigdxoxrcwmowxqcuiadl"

    # 路由 / 策略选择 置信度门控
    route_confidence_threshold: float = 0.8
    embed_confidence_threshold: float = 0.72  # 嵌入路由：top 相似度 ≥ 此值才直接路由
    strategy_confidence_threshold: float = 0.7

    # 调度引擎 (ReAct 智能体) 护栏
    react_max_steps: int = 8  # 思考-行动循环最大步数 (防无限循环/绕路)

    # 查询引擎 (RAG)
    rag_top_k: int = 3  # 每次检索返回的知识片段数

    # 事件层
    patrol_interval_seconds: float = 30.0
    kitting_lookahead_days: int = 3

    # 数据与日志
    mock_data_dir: Path = Field(default_factory=lambda: project_root() / "data" / "mock")
    knowledge_dir: Path = Field(
        default_factory=lambda: project_root() / "data" / "mock" / "knowledge"
    )
    audit_log_file: Path | None = Field(
        default_factory=lambda: project_root() / "logs" / "audit.jsonl"
    )
    sessions_dir: Path = Field(
        default_factory=lambda: project_root() / "data" / "sessions"
    )
