"""Capacity gate logic: character count and rough read-count estimate.

Kept pure (no DB / FastAPI imports) so it is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_chars: int
    max_reads: int


@dataclass(frozen=True)
class ContentSize:
    char_count: int
    read_estimate: int


def measure_content(text: str) -> ContentSize:
    """Measure pasted/sample content.

    字符数按去除首尾空白后的长度计；读段数为粗估——统计行首 ``@`` 的行数
    （FASTQ 每条记录的表头），不做完整解析，避免在校验阶段跑流水线。
    """
    stripped = (text or "").strip()
    if not stripped:
        return ContentSize(char_count=0, read_estimate=0)
    normalized = stripped.replace("\r\n", "\n").replace("\r", "\n")
    nonempty = sum(1 for line in normalized.split("\n") if line.strip())
    # FASTQ 每条读段固定 4 行；向上取整保证对合法输入只会高估、不漏拦。
    read_estimate = (nonempty + 3) // 4
    return ContentSize(char_count=len(stripped), read_estimate=read_estimate)


def check_limits(size: ContentSize, limits: Limits) -> str | None:
    """Return a human-readable rejection reason, or None when within limits."""
    if size.char_count > limits.max_chars:
        return (
            f"内容字符数 {size.char_count} 超过上限 {limits.max_chars}"
        )
    if size.read_estimate > limits.max_reads:
        return (
            f"粗估读段数 {size.read_estimate} 超过上限 {limits.max_reads}"
        )
    return None
