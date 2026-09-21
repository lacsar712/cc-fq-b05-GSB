"""Unit tests for the capacity-gate pure logic."""

from app.limits import Limits, check_limits, measure_content


GOOD_FASTQ = """@SEQ1
ACGTACGT
+
IIIIHHHH
@SEQ2
NNNNACGT
+
IIIIIIII
"""


def test_measure_empty_and_whitespace():
    assert measure_content("").char_count == 0
    assert measure_content("   \n\t ").char_count == 0
    assert measure_content("   \n\t ").read_estimate == 0


def test_measure_counts_chars_after_trim_and_reads():
    size = measure_content(f"  \n{GOOD_FASTQ}\n  ")
    # 2 reads x 4 lines
    assert size.read_estimate == 2
    # chars measured on the trimmed content
    assert size.char_count == len(GOOD_FASTQ.strip())


def test_check_limits_pass():
    size = measure_content(GOOD_FASTQ)
    assert check_limits(size, Limits(max_chars=10_000, max_reads=10)) is None


def test_check_limits_char_overflow():
    size = measure_content(GOOD_FASTQ)
    reason = check_limits(size, Limits(max_chars=10, max_reads=10_000))
    assert reason is not None
    assert "字符数" in reason


def test_check_limits_read_overflow():
    size = measure_content(GOOD_FASTQ)
    reason = check_limits(size, Limits(max_chars=10_000, max_reads=1))
    assert reason is not None
    assert "读段数" in reason


def test_estimate_ceil_groups_partial_blocks():
    # 5 non-empty lines -> ceil(5/4) = 2; rough estimate over-counts, never under
    size = measure_content("@A\nACGT\n+\nIIII\n@B")
    assert size.read_estimate == 2
