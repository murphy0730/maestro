"""文本切分 (RAG 摄取的第二步)。

把整篇文档切成适合嵌入检索的片段。策略: 先按 Markdown 标题层级分节 (保留
标题作为片段前缀，利于语义)，节内再按字符数滑窗切分并带重叠，避免把一句话
从中间切断导致检索召回下降。

纯文本无标题时退化为整篇滑窗。参数由 config 注入，便于后续调优。
"""

import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题分节，返回 (标题路径, 正文) 列表。无标题时单节。"""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    # 标题前的引言 (若有正文) 单独成节
    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if preface:
            sections.append(("", preface))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((heading, body))
    return sections


def _window(text: str, size: int, overlap: int) -> list[str]:
    """定长滑窗切分，尽量在段落/句子边界断开。"""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # 优先在窗口后半段的换行/句号处断开，避免切断句子
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind("。"), window.rfind(". "))
            if cut > size // 2:
                end = start + cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


class Chunker:
    """标题分节 + 定长重叠滑窗。产出片段带 section 元数据。"""

    def __init__(self, chunk_size: int = 500, overlap: int = 80, min_len: int = 10):
        self._size = chunk_size
        self._overlap = overlap
        self._min_len = min_len

    def split(self, text: str) -> list[tuple[str, dict]]:
        """切分为 (片段文本, 片段元数据) 列表。元数据含 section / chunk_index。"""
        out: list[tuple[str, dict]] = []
        for heading, body in _split_sections(text):
            for piece in _window(body, self._size, self._overlap):
                # 标题作为语义前缀拼进片段 (利于嵌入定位主题)
                chunk = f"{heading}\n{piece}" if heading else piece
                if len(chunk.strip()) >= self._min_len:
                    out.append((chunk, {"section": heading}))
        for i, (_, meta) in enumerate(out):
            meta["chunk_index"] = i
        return out
