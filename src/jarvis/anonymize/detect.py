"""Heuristic detection of column names that probably hold personal data."""

from __future__ import annotations

import re

PII_PATTERN: re.Pattern[str] = re.compile(
    r"mail|phone|mobile|tel|fax|surname|lastname|firstname|first_name|last_name"
    r"|address|birth|dob|passport|citizen|national|id_card|line_id",
    re.IGNORECASE,
)


def looks_like_pii(column: str) -> bool:
    """Return True when ``column`` looks like it carries personal data."""
    return PII_PATTERN.search(column) is not None
