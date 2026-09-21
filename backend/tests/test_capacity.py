"""Unit tests for the capacity gate helpers (no DB required)."""

from app.capacity import check_capacity, estimate_reads


GOOD_FASTQ = """@SEQ1
ACGTACGT
+
IIIIHHHH
@SEQ2
NNNNACGT
+
IIIIIIII
"""


def test_estimate_reads_counts_four_line_records():
    assert estimate_reads(GOOD_FASTQ) == 2
    assert estimate_reads("") == 0
    assert estimate_reads("   \n  ") == 1  # 粗估：纯按行数 / 4 向上取整
    assert estimate_reads("@A\nACGT\n+\nIIII") == 1
    # CRLF 与孤立 \r 同样按行统计
    assert estimate_reads("@A\r\nACGT\r\n+\r\nIIII\r\n") == 1


def test_check_capacity_within_limits_returns_none():
    assert check_capacity(GOOD_FASTQ, max_chars=200_000, max_reads=50_000) is None
    # 恰好等于上限不算超限
    text = "x" * 100
    assert check_capacity(text, max_chars=100, max_reads=25) is None


def test_check_capacity_char_limit():
    reason = check_capacity("x" * 101, max_chars=100, max_reads=10_000)
    assert reason is not None
    assert "字符数 101 超过上限 100" in reason


def test_check_capacity_read_limit():
    # 8 行 -> 粗估 2 条读段
    reason = check_capacity(GOOD_FASTQ, max_chars=200_000, max_reads=1)
    assert reason is not None
    assert "粗估读段数 2 超过上限 1" in reason


def test_check_capacity_reports_both_limits():
    reason = check_capacity(GOOD_FASTQ, max_chars=1, max_reads=1)
    assert reason is not None
    assert "字符数" in reason and "粗估读段数" in reason
