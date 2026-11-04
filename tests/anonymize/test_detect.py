"""Tests for the heuristic PII column-name detector."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.anonymize.detect import looks_like_pii  # noqa: E402


def test_detect_pii_names():
    for column in ("email", "B_phone", "dateofbirth", "line_id", "Surname"):
        assert looks_like_pii(column), column


def test_ignore_non_pii_names():
    for column in ("borrowernumber", "biblionumber", "title"):
        assert not looks_like_pii(column), column
