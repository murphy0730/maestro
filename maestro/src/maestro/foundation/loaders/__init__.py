"""文档加载层 —— 把各种类型的文件解析为纯文本 (RAG 摄取的第一步)。

业务侧 (KnowledgeIngestor) 只依赖 LoaderRegistry.load(path) → 文本，不感知具体
格式。新增格式 = 实现 DocumentLoader 并在 build_loader_registry() 注册一行。

零依赖格式 (md/txt/csv/html) 恒可用；pdf/docx 依赖第三方库，缺库时对应 loader
不注册 —— 该后缀会被当作「不支持」拒绝，与平台整体的离线降级哲学一致。
"""

from maestro.foundation.loaders.base import (
    DocumentLoader,
    LoaderRegistry,
    UnsupportedFileType,
    build_loader_registry,
)

__all__ = [
    "DocumentLoader",
    "LoaderRegistry",
    "UnsupportedFileType",
    "build_loader_registry",
]
