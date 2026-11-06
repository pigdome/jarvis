"""Drive a dump through the engine's rewriter, poisoning the output on failure.

stdout carries SQL only.  When the dump cannot be parsed safely the driver
closes whatever block is still open, emits a statement that cannot execute
(``JARVIS_ANONYMIZE_FAILED;``) and re-raises, so a restore pipeline fails
loudly instead of restoring a half-anonymized dump.
"""

from __future__ import annotations

import itertools
import time
from typing import BinaryIO

from .errors import DumpFormatError
from .mysql_stream import MysqlRewriter
from .pg_stream import PgRewriter
from .profile import Profile
from .report import Report
from .strategies import Faker

POISON_SQL = b"JARVIS_ANONYMIZE_FAILED;\n"

# Header lines that identify the dump's engine. Checked before anything is
# written, so a wrong-engine dump never reaches the restore client (its text
# could leave the client inside an open quote and swallow the poison).
_MYSQL_MARKERS = (b"-- MySQL dump", b"-- MariaDB dump", b"/*M!", b"/*!40")
_PG_MARKERS = (b"-- PostgreSQL database dump", b"\\restrict ", b"SET statement_timeout")
_SNIFF_LINES = 40


def _sniff_engine(lines: list[bytes]) -> str | None:
    for line in lines:
        if line.startswith(_MYSQL_MARKERS):
            return "mysql"
        if line.startswith(_PG_MARKERS):
            return "psql"
    return None


def _make_rewriter(
    profile: Profile, faker: Faker, report: Report
) -> MysqlRewriter | PgRewriter:
    if profile.engine == "mysql":
        return MysqlRewriter(profile, faker, report)
    return PgRewriter(profile, faker, report)


def _comment(exc: BaseException) -> bytes:
    message = " ".join(str(exc).split())
    return b"-- jarvis db anonymize FAILED: " + message.encode("utf-8", "replace") + b"\n"


def _poison(
    profile: Profile,
    rewriter: MysqlRewriter | PgRewriter,
    exc: BaseException,
) -> bytes:
    """Return bytes that make the downstream restore fail."""
    if profile.engine == "mysql":
        return _comment(exc) + POISON_SQL

    parts: list[bytes] = []
    if rewriter.in_copy:
        parts.append(b"\\.\n")
    if rewriter.restrict_key:
        parts.append(
            b"\\unrestrict " + rewriter.restrict_key.encode("utf-8", "replace") + b"\n"
        )
    parts.append(b"\\set ON_ERROR_STOP on\n")
    parts.append(_comment(exc))
    parts.append(POISON_SQL)
    return b"".join(parts)


def run_stream(
    profile: Profile,
    inp: BinaryIO,
    out: BinaryIO,
    faker: Faker | None = None,
) -> Report:
    """Rewrite ``inp`` into ``out``; on a parse failure poison ``out`` and raise."""
    report = Report(profile=profile.name)
    if faker is None:
        faker = Faker(email_tld=profile.email_tld)
    rewriter = _make_rewriter(profile, faker, report)

    started = time.perf_counter()
    try:
        lines = iter(inp)
        head: list[bytes] = []
        for line in lines:
            head.append(line)
            if len(head) >= _SNIFF_LINES:
                break
        detected = _sniff_engine(head)
        if detected is not None and detected != profile.engine:
            raise DumpFormatError(
                f"this looks like a {detected} dump but profile "
                f"{profile.name!r} is for {profile.engine}"
            )
        for line in itertools.chain(head, lines):
            report.bytes_in += len(line)
            chunk = rewriter.feed(line)
            if chunk is not None:
                out.write(chunk)
        rewriter.finish()
    except BrokenPipeError:
        raise
    except Exception as exc:
        # Any failure (not only DumpFormatError) must poison the output so a
        # restore pipeline cannot finish with a truncated dump.
        report.seconds = time.perf_counter() - started
        try:
            out.flush()
            out.write(_poison(profile, rewriter, exc))
            out.flush()
        except BrokenPipeError:
            pass
        if isinstance(exc, DumpFormatError):
            raise
        raise DumpFormatError(f"internal error: {type(exc).__name__}: {exc}") from exc
    report.seconds = time.perf_counter() - started
    out.flush()
    return report
