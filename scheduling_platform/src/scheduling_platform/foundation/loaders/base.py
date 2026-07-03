"""文档加载器接口 + 按后缀分派的注册表。

DocumentLoader 只有一个职责: 字节流 → 纯文本。切分 (chunking) 与嵌入是后续
环节，不在这里做。加载器拿字节而非路径，好处是上传流 (前端 multipart) 和本地
文件都能复用同一条管线，无需先落盘。
"""

import csv
import io
import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class UnsupportedFileType(Exception):
    """文件后缀没有对应的已注册加载器。"""

    def __init__(self, ext: str, supported: list[str]):
        self.ext = ext
        self.supported = supported
        super().__init__(f"不支持的文件类型 '{ext}'，已支持: {', '.join(supported) or '无'}")


@runtime_checkable
class DocumentLoader(Protocol):
    """把某类文件的字节解析为纯文本。extensions 为小写、带点的后缀元组。"""

    extensions: tuple[str, ...]

    def load(self, data: bytes, filename: str) -> str: ...


def _ext_of(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot >= 0 else ""


class TextLoader:
    """纯文本 / Markdown —— 直接按 UTF-8 解码 (容错非法字节)。"""

    extensions = (".md", ".markdown", ".txt", ".text", ".log")

    def load(self, data: bytes, filename: str) -> str:
        return data.decode("utf-8", errors="replace")


class CsvLoader:
    """CSV —— 逐行拼成 "列: 值" 文本，让表格内容能被嵌入检索。"""

    extensions = (".csv",)

    def load(self, data: bytes, filename: str) -> str:
        text = data.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return ""
        header = rows[0]
        lines: list[str] = []
        for row in rows[1:]:
            pairs = [f"{h}: {v}" for h, v in zip(header, row) if v]
            if pairs:
                lines.append(" | ".join(pairs))
        # 无数据行时 (只有表头) 退化为表头本身，避免空文档
        return "\n".join(lines) if lines else " | ".join(header)


class HtmlLoader:
    """HTML —— 用标准库 HTMLParser 剥标签取正文 (零第三方依赖)。"""

    extensions = (".html", ".htm")

    def load(self, data: bytes, filename: str) -> str:
        from html.parser import HTMLParser

        skip = {"script", "style", "head", "meta", "link"}

        class _Extractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []
                self._skip_depth = 0

            def handle_starttag(self, tag: str, attrs: object) -> None:
                if tag in skip:
                    self._skip_depth += 1

            def handle_endtag(self, tag: str) -> None:
                if tag in skip and self._skip_depth > 0:
                    self._skip_depth -= 1

            def handle_data(self, data: str) -> None:
                if self._skip_depth == 0 and data.strip():
                    self.parts.append(data.strip())

        parser = _Extractor()
        parser.feed(data.decode("utf-8", errors="replace"))
        return "\n".join(parser.parts)


class PdfLoader:
    """PDF —— 依赖 pypdf，逐页抽取文本。缺库时注册阶段跳过。"""

    extensions = (".pdf",)

    def load(self, data: bytes, filename: str) -> str:
        from pypdf import PdfReader  # 延迟导入: 缺库不影响其它加载器

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(p.strip() for p in pages if p.strip())


class DocxLoader:
    """DOCX —— 依赖 python-docx，抽取段落文本。缺库时注册阶段跳过。"""

    extensions = (".docx",)

    def load(self, data: bytes, filename: str) -> str:
        import docx  # 延迟导入

        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text.strip() for p in document.paragraphs if p.text.strip())


class LoaderRegistry:
    """按文件后缀分派到具体加载器。"""

    def __init__(self) -> None:
        self._by_ext: dict[str, DocumentLoader] = {}

    def register(self, loader: DocumentLoader) -> None:
        for ext in loader.extensions:
            self._by_ext[ext.lower()] = loader

    @property
    def supported_extensions(self) -> list[str]:
        return sorted(self._by_ext.keys())

    def supports(self, filename: str) -> bool:
        return _ext_of(filename) in self._by_ext

    def load(self, data: bytes, filename: str) -> str:
        ext = _ext_of(filename)
        loader = self._by_ext.get(ext)
        if loader is None:
            raise UnsupportedFileType(ext or "(无后缀)", self.supported_extensions)
        return loader.load(data, filename)


def _try_register_optional(registry: LoaderRegistry, loader: DocumentLoader) -> None:
    """探测可选加载器依赖是否就绪 (import 一次)，缺库则跳过注册。"""
    try:
        # 用一个最小字节流触发延迟 import；失败即视为依赖缺失
        loader.load(b"", "__probe__" + loader.extensions[0])
    except ImportError:
        logger.info("[LOADERS] 依赖缺失，跳过 %s (%s)", type(loader).__name__, loader.extensions)
        return
    except Exception:  # noqa: BLE001 — 依赖在但空字节解析报错，说明库可用，照常注册
        pass
    registry.register(loader)


def build_loader_registry() -> LoaderRegistry:
    """构造默认注册表: 零依赖格式恒注册，pdf/docx 按依赖可用性注册。"""
    registry = LoaderRegistry()
    for loader in (TextLoader(), CsvLoader(), HtmlLoader()):
        registry.register(loader)
    for optional in (PdfLoader(), DocxLoader()):
        _try_register_optional(registry, optional)
    logger.info("[LOADERS] 已启用后缀: %s", registry.supported_extensions)
    return registry
