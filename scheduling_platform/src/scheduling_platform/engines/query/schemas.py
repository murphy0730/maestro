"""查询引擎数据模型。"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class QuerySource(BaseModel):
    """RAG 回答引用的知识来源片段 (用于「答案附来源」)。"""

    doc: str  # 来源文档名
    score: float  # 检索相似度
    excerpt: str = ""  # 片段摘录 (截断)


DocStatus = Literal["ready", "failed"]


class KnowledgeDoc(BaseModel):
    """知识库中的一篇文档 (前端增删改查列表项)。"""

    doc_id: str
    name: str
    type: str  # 文件后缀 (不含点): md / pdf / docx ...
    chunk_count: int = 0
    bytes: int = 0
    status: DocStatus = "ready"  # failed = 嵌入未配置，未参与检索
    added_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
