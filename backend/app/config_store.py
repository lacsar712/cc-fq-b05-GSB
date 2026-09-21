"""Persisted runtime configuration (capacity gate), with self-healing defaults."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.limits import Limits
from app.models import DEFAULT_MAX_CHARS, DEFAULT_MAX_READS, LIMITS_CONFIG_KEY, SystemConfig


DEFAULT_LIMITS = Limits(max_chars=DEFAULT_MAX_CHARS, max_reads=DEFAULT_MAX_READS)


def _row(db: Session) -> SystemConfig | None:
    return (
        db.query(SystemConfig)
        .filter(SystemConfig.config_key == LIMITS_CONFIG_KEY)
        .one_or_none()
    )


def ensure_default_limits(db: Session) -> Limits:
    """Make sure the limits row exists; create it from defaults if absent/broken."""
    row = _row(db)
    if row is None:
        limits = DEFAULT_LIMITS
        db.add(
            SystemConfig(
                config_key=LIMITS_CONFIG_KEY,
                config_value=json.dumps(
                    {"max_chars": limits.max_chars, "max_reads": limits.max_reads}
                ),
            )
        )
        db.commit()
        return limits
    try:
        data = json.loads(row.config_value)
        return Limits(max_chars=int(data["max_chars"]), max_reads=int(data["max_reads"]))
    except (ValueError, KeyError, TypeError):
        # Corrupt row: heal to defaults rather than blocking every submission.
        limits = DEFAULT_LIMITS
        row.config_value = json.dumps(
            {"max_chars": limits.max_chars, "max_reads": limits.max_reads}
        )
        db.commit()
        return limits


def get_limits(db: Session) -> Limits:
    row = _row(db)
    if row is None:
        return ensure_default_limits(db)
    try:
        data = json.loads(row.config_value)
        return Limits(max_chars=int(data["max_chars"]), max_reads=int(data["max_reads"]))
    except (ValueError, KeyError, TypeError):
        return ensure_default_limits(db)


def save_limits(db: Session, max_chars: int, max_reads: int, username: str) -> Limits:
    limits = Limits(max_chars=max_chars, max_reads=max_reads)
    row = _row(db)
    payload = json.dumps({"max_chars": max_chars, "max_reads": max_reads})
    if row is None:
        db.add(
            SystemConfig(
                config_key=LIMITS_CONFIG_KEY,
                config_value=payload,
                updated_by=username,
            )
        )
    else:
        row.config_value = payload
        row.updated_by = username
    db.commit()
    return limits
