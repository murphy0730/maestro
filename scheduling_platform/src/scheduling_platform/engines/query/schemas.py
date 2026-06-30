"""查询引擎数据模型。"""

from pydantic import BaseModel


class QuerySource(BaseModel):
    """RAG 回答引用的知识来源片段 (用于「答案附来源」)。"""

    doc: str  # 来源文档名
    score: float  # 检索相似度
    excerpt: str = ""  # 片段摘录 (截断)
