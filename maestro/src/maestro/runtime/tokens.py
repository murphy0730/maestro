"""Dependency-free prompt size estimation.

Deliberately not tiktoken: it is OpenAI's tokenizer, no more accurate against
DeepSeek or Qwen than a calibrated heuristic, and it costs a heavy dependency.
The estimate drives *budget decisions*; ``resp.usage`` reported by the provider
is recorded next to it so the drift between the two stays visible instead of
being assumed away.

The coefficients below were measured against deepseek-v4-pro by differential
probing (`model.turn` events carry estimate and `usage` side by side so the
drift stays observable).  Measured residual on representative prompts: between
-2% and +65%, the large positive end being short prompts where a fixed overhead
dominates and the absolute error is a few tokens.

This is a best fit, **not** a guaranteed upper bound — an isolated ASCII letter
between CJK runs costs a full token rather than the quarter charged here, so
dense mixed text can come in ~2% under.  The safety margin against overflow
belongs in the budget that consumes these numbers, where it is explicit and
configurable, not hidden inside the estimator.
"""

from __future__ import annotations

import json
from math import ceil

# Three measured rates. One rate cannot fit both English prose (~0.2 tok/char)
# and mixed Chinese/digit text (~0.47 tok/char); charging everything at the
# higher rate over-billed English source files — which `read_file` puts into
# context routinely — by roughly double.
_CJK_TOKENS_PER_CHAR = 1.0  # measured exactly 1.000
_WORD_TOKENS_PER_CHAR = 0.25  # ASCII letters; measured ~0.2
# Digits, punctuation, whitespace, everything else; measured ~0.47. Whitespace
# belongs here, not with letters: a space merges into the following word token
# in English prose but not between CJK runs, and the mixed case is the one that
# must not be under-counted.
_SYMBOL_TOKENS_PER_CHAR = 0.5

# Measured ~0.3 tokens per message. Kept at 4 (the OpenAI convention) because
# the margin is negligible and errs high.
_MESSAGE_OVERHEAD = 4

# Measured: declaring *any* tool costs ~221 tokens before the first schema, then
# ~64 tokens per additional tool on top of its serialized content. Folded into
# one fixed block plus a full-rate content charge, which lands ~25% high.
_TOOLS_FIXED_OVERHEAD = 256


def _is_cjk(char: str) -> bool:
    """Han characters, CJK punctuation and fullwidth forms all cost ~1 token."""
    code = ord(char)
    return (
        0x3000 <= code <= 0x303F  # CJK punctuation （）【】、。
        or 0x4E00 <= code <= 0x9FFF  # CJK unified ideographs
        or 0xFF00 <= code <= 0xFFEF  # fullwidth forms ；：？！
    )


def estimate_tokens(text: str) -> int:
    """Approximate tokens for `text`, rounding high."""
    if not text:
        return 0
    total = 0.0
    for char in text:
        if _is_cjk(char):
            total += _CJK_TOKENS_PER_CHAR
        elif char.isascii() and char.isalpha():
            total += _WORD_TOKENS_PER_CHAR
        else:
            total += _SYMBOL_TOKENS_PER_CHAR
    return ceil(total)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate a chat array, counting the per-message envelope the API adds."""
    total = 0
    for message in messages:
        total += _MESSAGE_OVERHEAD
        for value in message.values():
            total += estimate_tokens(
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False, default=str)
            )
    return total


def estimate_tools_tokens(tools: list[dict]) -> int:
    """Estimate the tool schema array, which is billed as part of the prompt.

    Invisible to every budget until now, yet it is the single largest fixed cost
    in a Run's prompt and grows with each installed Skill: one description alone
    may run to 1024 chars (`skills/schemas.py`).
    """
    if not tools:
        return 0
    return _TOOLS_FIXED_OVERHEAD + estimate_tokens(
        json.dumps(tools, ensure_ascii=False, default=str)
    )
