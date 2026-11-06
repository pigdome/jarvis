#!/usr/bin/env python3
"""Benchmark ``jarvis db anonymize`` stream mode on synthetic Koha dumps.

The script expands the committed mysqldump fixture to two ~200 MB dumps in
``OUTDIR`` (default: the system temp dir), then times three runs:

  (a) passthrough  — realistic dump, a profile with no rules at all
  (b) koha         — the same realistic dump through the bundled koha profile
  (c) koha worst   — a borrowers-heavy dump through the bundled koha profile

The realistic dump is biblio-heavy, like a production Koha dump where
``biblio_metadata`` dominates the bytes and every one of them is passed
through untouched.  The borrowers-heavy dump is the opposite extreme: every
line is an extended INSERT whose cells all carry a rule.

Usage:

    python3 tests/anonymize/bench_stream.py [OUTDIR]

Target (a) and (b) at >= 20 MB/s.  (c) is reported as-is; it is the worst case,
not a regression gate.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "src"))

from jarvis.anonymize.profile import Profile, load_profile  # noqa: E402
from jarvis.anonymize.stream import run_stream  # noqa: E402

FIXTURE = HERE.parents[1] / "fixtures" / "anonymize" / "mysql_dump.sql"
TARGET_BYTES = 200 * 1000 * 1000
TARGET_RATE = 20.0

_SECTION_RE = re.compile(rb"^--\n-- Table structure for table `([^`]+)`\n", re.M)
_BORROWER_PREFIX_RE = re.compile(
    rb"^\((\d+|NULL),('(?:[^'\\]|\\.)*'|NULL),('(?:[^'\\]|\\.)*'|NULL),"
)
_BIBLIO_PREFIX_RE = re.compile(rb"^\((\d+|NULL),")

# Filler for the unruled table: enough text per row that biblio dominates the
# dump, the way biblio_metadata's MARC blob does in a real Koha database.
_BIBLIO_TEXT = (
    "The administration of academic libraries in the digital age: collection "
    "development, metadata workflows, electronic resource management, patron "
    "services, staff training, building maintenance, budgeting, and the daily "
    "operations of a university library consortium in Southeast Asia. "
    "Proceedings of the annual conference on library automation and open "
    "access repositories, with appendices on MARC formats, authority control, "
    "interlibrary loan networks, and preservation of local history archives. "
) * 4


def split_sections(dump: bytes) -> tuple[bytes, dict[str, tuple[bytes, bytes, bytes]]]:
    """Split a mysqldump into preamble and per-table (head, rows, tail).

    ``head`` is everything up to the first INSERT of that table, ``tail`` is
    everything after the last INSERT statement.  Row lines are returned
    normalised (``(…)`` without the trailing comma/semicolon).
    """
    matches = list(_SECTION_RE.finditer(dump))
    if not matches:
        raise SystemExit(f"no CREATE TABLE sections found in {FIXTURE}")
    preamble = dump[: matches[0].start()]
    sections: dict[str, tuple[bytes, bytes, bytes]] = {}
    for index, match in enumerate(matches):
        table = match.group(1).decode("utf-8", "surrogateescape")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(dump)
        sections[table] = _split_table(dump[match.start() : end], table)
    return preamble, sections


def _split_table(section: bytes, table: str) -> tuple[bytes, bytes, bytes]:
    marker = b"\nINSERT INTO `" + table.encode("utf-8") + b"` VALUES"
    first = section.find(marker)
    if first == -1:
        return section, b"", b""
    body_start = first + 1
    lines = section[body_start:].splitlines(keepends=True)
    rows: list[bytes] = []
    index = 0
    for index, line in enumerate(lines):
        if line.startswith(b"INSERT INTO `"):
            continue
        if line.startswith(b"("):
            rows.append(line.strip().rstrip(b",;"))
            continue
        break
    return section[:body_start], b"\n".join(rows), b"".join(lines[index:])


def _write_inserts(out, table: str, rows: Iterable[bytes], batch: int) -> None:
    pending: list[bytes] = []
    for row in rows:
        pending.append(row)
        if len(pending) == batch:
            out.write(b"INSERT INTO `" + table.encode() + b"` VALUES\n")
            out.write(b",\n".join(pending))
            out.write(b";\n")
            pending = []
    if pending:
        out.write(b"INSERT INTO `" + table.encode() + b"` VALUES\n")
        out.write(b",\n".join(pending))
        out.write(b";\n")


def _borrower_rows(base: list[bytes], count: int, start: int) -> Iterable[bytes]:
    """Cycle the seeded rows, renumbering the key columns so they stay unique."""
    for offset in range(count):
        number = start + offset
        row = base[offset % len(base)]
        card = 9000000000 + number
        yield _BORROWER_PREFIX_RE.sub(
            b"(%d,'%d','u%d'," % (number, card, number), row, count=1
        )


def _biblio_rows(base: list[bytes], count: int, start: int) -> Iterable[bytes]:
    """Large unruled rows: a biblio_metadata-sized payload per record."""
    for number in range(start, start + count):
        row = base[(number - 1) % len(base)]
        row = _BIBLIO_PREFIX_RE.sub(b"(%d," % number, row, count=1)
        head, _, _ = row.partition(b",")
        yield head + b",'" + _BIBLIO_TEXT.encode() + b"','Synthetic Author')"


def build_realistic(path: Path, preamble: bytes, sections) -> None:
    """Biblio-heavy dump: ~99% of the bytes are an unruled table."""
    biblio_head, biblio_rows, biblio_tail = sections["biblio"]
    base_rows = biblio_rows.split(b"\n") if biblio_rows else []
    reserve = 3_000_000
    with open(path, "wb") as out:
        out.write(preamble)
        out.write(biblio_head)
        number = 0
        while out.tell() < TARGET_BYTES - reserve:
            chunk = min(1000, max(1, (TARGET_BYTES - reserve - out.tell()) // 1200))
            rows = _biblio_rows(base_rows, chunk, start=number + 1)
            _write_inserts(out, "biblio", rows, batch=100)
            number += chunk
        out.write(biblio_tail)
        for table in ("borrower_attributes", "borrowers", "issues", "sessions"):
            head, rows, tail = sections[table]
            out.write(head)
            if rows:
                clean = rows.split(b"\n")
                if table == "borrowers":
                    clean = list(_borrower_rows(clean, len(clean), 1))
                _write_inserts(out, table, clean, batch=250)
            out.write(tail)


def build_borrowers_heavy(path: Path, preamble: bytes, sections) -> None:
    """Worst case: every byte sits in an extended INSERT with rules."""
    with open(path, "wb") as out:
        out.write(preamble)
        for table in ("biblio", "borrower_attributes"):
            head, rows, tail = sections[table]
            out.write(head)
            if rows:
                _write_inserts(out, table, rows.split(b"\n"), batch=250)
            out.write(tail)

        head, rows, tail = sections["borrowers"]
        base = rows.split(b"\n")
        out.write(head)
        number = 1
        while out.tell() < TARGET_BYTES - 2_000_000:
            count = max(len(base), (TARGET_BYTES - out.tell()) // 1200)
            _write_inserts(out, "borrowers", _borrower_rows(base, count, number), 250)
            number += count
        out.write(tail)
        for table in ("issues", "sessions"):
            head, rows, tail = sections[table]
            out.write(head)
            if rows:
                _write_inserts(out, table, rows.split(b"\n"), batch=250)
            out.write(tail)


def _passthrough_profile() -> Profile:
    return Profile(
        name="passthrough",
        engine="mysql",
        description="no rules — measures the stream driver",
        truncate=frozenset(),
        email_tld="invalid",
        tables={},
    )


def measure(label: str, profile: Profile, source: Path, out_path: Path) -> float:
    size = source.stat().st_size
    started = time.perf_counter()
    with open(source, "rb") as inp, open(out_path, "wb") as out:
        run_stream(profile, inp, out)
    elapsed = time.perf_counter() - started
    megabytes = size / 1_000_000
    rate = megabytes / elapsed if elapsed else float("inf")
    print(
        f"{label:<16} {megabytes:8.1f} MB  {elapsed:7.2f} s  {rate:8.1f} MB/s",
        flush=True,
    )
    return rate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "outdir",
        nargs="?",
        default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "jarvis-anon-bench"),
        help="directory for the generated dumps (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    preamble, sections = split_sections(FIXTURE.read_bytes())
    realistic = outdir / "bench_realistic.sql"
    heavy = outdir / "bench_borrowers.sql"
    if not realistic.exists():
        print(f"building {realistic} …", flush=True)
        build_realistic(realistic, preamble, sections)
    if not heavy.exists():
        print(f"building {heavy} …", flush=True)
        build_borrowers_heavy(heavy, preamble, sections)

    koha = load_profile("koha")
    output = outdir / "bench_out.sql"

    print(f"{'run':<16} {'size':>11}  {'time':>8}  {'rate':>11}")
    passthrough = measure("(a) passthrough", _passthrough_profile(), realistic, output)
    koha_realistic = measure("(b) koha", koha, realistic, output)
    koha_heavy = measure("(c) koha worst", koha, heavy, output)
    output.unlink(missing_ok=True)

    ok = passthrough >= TARGET_RATE and koha_realistic >= TARGET_RATE
    verdict = "OK" if ok else "SLOW"
    print(
        f"\n{verdict}: (a) {passthrough:.1f} MB/s, (b) {koha_realistic:.1f} MB/s, "
        f"(c) {koha_heavy:.1f} MB/s (target {TARGET_RATE:.0f} MB/s for a and b)"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
