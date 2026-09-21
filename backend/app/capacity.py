"""Capacity gate helpers for pasted/sample FASTQ content (pure, no DB imports)."""

from __future__ import annotations

# Defaults for the persisted capacity_config row (created lazily on first read).
DEFAULT_MAX_CHARS = 200_000
DEFAULT_MAX_READS = 50_000

# Rejected drafts keep only a short preview of the oversized input.
REJECTED_SNAPSHOT_PREVIEW_CHARS = 500


def estimate_reads(text: str) -> int:
    """Rough read-count estimate: FASTQ is 4 lines per record, so ceil(lines / 4)."""
    if not text:
        return 0
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return (len(lines) + 3) // 4


def check_capacity(text: str, max_chars: int, max_reads: int) -> str | None:
    """Return a human-readable rejection reason if text exceeds limits, else None."""
    reasons: list[str] = []
    char_count = len(text)
    if char_count > max_chars:
        reasons.append(f"字符数 {char_count} 超过上限 {max_chars}")
    est = estimate_reads(text)
    if est > max_reads:
        reasons.append(f"粗估读段数 {est} 超过上限 {max_reads}")
    return "；".join(reasons) if reasons else None
