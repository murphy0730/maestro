"""嵌入语义路由 (意图路由第 1 层)。

把用户输入向量化，与各意图的种子例句算最大余弦相似度，取最高分意图。
相比关键词规则: 对换说法/同义词鲁棒、置信度连续可校准、加例句即可扩展。
例句向量首次使用时一次性批量嵌入并缓存 (后续仅嵌入用户输入这一条)。
"""

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from maestro.foundation.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

DEFAULT_EXAMPLES_PATH = Path(__file__).with_name("routing_examples.yaml")
MIN_MARGIN = 0.05  # top1 与 top2 意图相似度差小于此值视为难分 → 交 LLM


def load_examples(path: Path | None = None) -> dict[str, list[str]]:
    raw = yaml.safe_load((path or DEFAULT_EXAMPLES_PATH).read_text(encoding="utf-8")) or {}
    return {intent: list(sents) for intent, sents in raw.items() if sents}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class EmbedResult:
    intent: str
    score: float  # top 意图的最大余弦相似度
    margin: float  # top1 与 top2 意图的相似度差
    scores: dict[str, float]

    @property
    def confident(self) -> bool:
        return self.margin >= MIN_MARGIN


class EmbeddingRouter:
    def __init__(self, llm: LLMClient, examples: dict[str, list[str]] | None = None,
                 skills=None):
        self._llm = llm
        self._examples = examples or {}
        self._vectors: dict[str, list[list[float]]] | None = None
        self._skills = skills
        self._skill_version: int | None = None

    @property
    def available(self) -> bool:
        return self._llm.embed_available and bool(self._examples)

    async def _ensure_vectors(self) -> None:
        if self._vectors is None:
            flat = [(intent, s) for intent, sents in self._examples.items() for s in sents]
            vecs = await self._llm.embed([s for _, s in flat])
            store: dict[str, list[list[float]]] = {}
            for (intent, _), v in zip(flat, vecs):
                store.setdefault(intent, []).append(v)
            self._vectors = store
            logger.info("[EMBED] 种子例句已向量化: %s", {k: len(v) for k, v in store.items()})
        # 技能向量按 store.version 拉式失效: 每次 classify 都比对 version,
        # 变了就丢弃旧 skill: 键重嵌 (skills=None 时为 no-op)。
        await self._ensure_skill_vectors()

    async def _ensure_skill_vectors(self) -> None:
        assert self._vectors is not None
        if self._skills is None or self._skill_version == self._skills.version:
            return
        for k in [k for k in self._vectors if k.startswith("skill:")]:
            del self._vectors[k]
        examples = self._skills.routing_examples()
        if examples:
            flat = [(intent, s) for intent, sents in examples.items() for s in sents]
            vecs = await self._llm.embed([s for _, s in flat])
            for (intent, _), v in zip(flat, vecs):
                self._vectors.setdefault(intent, []).append(v)
        self._skill_version = self._skills.version
        logger.info("[EMBED] 技能例句已向量化 (version=%d)", self._skill_version)

    async def classify(self, message: str) -> EmbedResult:
        """对用户输入做语义路由。失败时抛 LLMError (由调用方降级到 LLM 层)。"""
        await self._ensure_vectors()
        assert self._vectors is not None
        qv = (await self._llm.embed([message]))[0]
        scores = {
            intent: max(_cosine(qv, v) for v in vecs)
            for intent, vecs in self._vectors.items()
        }
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_intent, top_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        result = EmbedResult(
            intent=top_intent, score=top_score, margin=top_score - second, scores=scores
        )
        logger.info(
            "[EMBED] → %s score=%.3f margin=%.3f scores=%s",
            result.intent, result.score, result.margin,
            {k: round(v, 3) for k, v in scores.items()},
        )
        return result
