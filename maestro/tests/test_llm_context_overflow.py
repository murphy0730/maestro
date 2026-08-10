"""上下文超长必须与一般 LLM 故障区分开。"""

from maestro.foundation.llm import LLMContextOverflow, LLMError, _is_context_overflow


class _Coded(Exception):
    def __init__(self, code: str) -> None:
        super().__init__("boom")
        self.code = code


def test_overflow_is_a_kind_of_llm_error() -> None:
    """既有 `except LLMError` 的调用方不会因新子类而漏接。"""
    assert issubclass(LLMContextOverflow, LLMError)


def test_recognised_by_provider_error_code() -> None:
    assert _is_context_overflow(_Coded("context_length_exceeded"))


def test_recognised_by_message_text() -> None:
    # OpenAI 兼容实现之间文案不统一，因此按多个标记匹配。
    assert _is_context_overflow(Exception("This model's maximum context length is 65536 tokens"))
    assert _is_context_overflow(Exception("Please reduce the length of the messages"))


def test_ordinary_failures_are_not_mistaken_for_overflow() -> None:
    assert not _is_context_overflow(Exception("connection reset by peer"))
    assert not _is_context_overflow(_Coded("invalid_api_key"))
