from maestro.runtime.tokens import (
    estimate_messages_tokens,
    estimate_tokens,
    estimate_tools_tokens,
)


def test_empty_text_costs_nothing():
    assert estimate_tokens("") == 0


def test_cjk_counts_about_one_token_per_character():
    assert estimate_tokens("生产计划排产调度") == 8


def test_english_prose_counts_about_one_token_per_four_characters():
    """Measured ~0.2 tok/char; letters and spaces tokenize efficiently."""
    assert estimate_tokens("abcdefgh") == 2


def test_digits_and_punctuation_cost_twice_what_letters_do():
    """Measured ~0.47 tok/char; a single rate for all ASCII fits neither shape."""
    assert estimate_tokens("12345678") == 4


def test_mixed_text_adds_all_scripts():
    # 4 CJK chars + 8 ASCII letters -> 4 + 2
    assert estimate_tokens("排产调度abcdefgh") == 6


def test_cjk_punctuation_and_fullwidth_forms_cost_a_full_token():
    """They tokenize like han characters, not like ASCII."""
    assert estimate_tokens("，。；：") == 4


def test_tracks_the_measured_rate_on_real_scheduling_text():
    """deepseek-v4-pro billed this shape at 0.652 tok/char (1500 for 2300 chars).

    Held to a band, not a one-sided bound: an isolated ASCII letter between CJK
    runs costs a full token, so the estimate lands ~2% low here. The margin
    against overflow lives in the budget, not in this function.
    """
    segment = "物料A 数量100 交期2026-08-10；"
    measured = len(segment) * 100 * 0.652
    assert 0.95 * measured <= estimate_tokens(segment * 100) <= 1.15 * measured


def test_messages_include_the_per_message_envelope():
    # Each message carries a fixed role/delimiter overhead, so two empty
    # messages still cost more than nothing.
    assert estimate_messages_tokens([{"role": "user", "content": ""}]) > 0


def test_messages_count_non_string_values():
    """A tool_calls payload is billed like any other content."""
    plain = estimate_messages_tokens([{"role": "assistant", "content": ""}])
    with_calls = estimate_messages_tokens(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "read_file"}}],
            }
        ]
    )
    assert with_calls > plain


def test_tools_schema_carries_a_large_fixed_overhead():
    """Declaring any tool at all was measured at ~285 tokens for one small tool.

    Sizing tools by their serialized length alone underestimated this by ~70%,
    which is the direction that lets a prompt overflow.
    """
    assert estimate_tools_tokens([]) == 0
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读取工作区内的一个文件",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }
    ]
    assert estimate_tools_tokens(tools) >= 285
