"""Tests for `jarvis sys skill-audit` (no real SkillSpector required)."""

import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "skillspector_report.json"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jarvis.commands import skill_audit as sa  # noqa: E402


def make_skill(base: Path, name: str = "demo") -> Path:
    path = base / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    return path


def make_report(name: str = "safe", score: int = 0, severity: str = "low",
                recommendation: str = "SAFE", findings=None, error=None):
    return sa.SkillReport(
        path=Path("/home/u/.claude/skills") / name,
        name=name,
        family="claude",
        score=score,
        severity=severity,
        recommendation=recommendation,
        findings=findings or [],
        error=error,
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_discovery_prunes_noise_dirs(tmp_path):
    root = tmp_path / "root"
    expected = make_skill(root, "good")
    for noise in (
        "node_modules/pkg", ".git/hooks", "venv/lib", ".venv/lib", "__pycache__/x",
        ".cache/x", ".npm/x", "snap/x", "Dropbox/x", "site-packages/x",
        "dist/x", "build/x",
    ):
        make_skill(root / noise, "skill")

    assert sa.discover_skills(root) == [expected.resolve()]


def test_discovery_excludes_builtin_unless_requested(tmp_path):
    root = tmp_path / "root"
    keep = make_skill(root, "keep")
    builtin = [
        make_skill(root / ".vscode/extensions/ext", "vsc"),
        make_skill(root / ".cursor/extensions/ext", "cur"),
        make_skill(root / ".gemini/antigravity/1.0/builtin/skills", "gem"),
        make_skill(root / ".codex/skills/.system", "sys"),
        make_skill(root / ".cursor/skills-cursor", "cursor-skill"),
    ]

    assert sa.discover_skills(root, include_builtin=False) == [keep.resolve()]

    found = sa.discover_skills(root, include_builtin=True)
    assert {p.resolve() for p in found} == {keep.resolve()} | {p.resolve() for p in builtin}


def test_discovery_always_prunes_tmp_and_vendor_trees(tmp_path):
    home = tmp_path / "home"
    keep = make_skill(home, "keep")
    for relative in (
        "tmp/x", ".tmp/x", "project/tmp/x", "project/.tmp/x",
        ".local/lib/x", ".local/share/uv/x", "orca/workspaces/x",
    ):
        make_skill(home / relative, "skill")

    assert sa.discover_skills(home, home=home) == [keep.resolve()]
    assert sa.discover_skills(home, include_builtin=True, home=home) == [keep.resolve()]


def test_discovery_treats_plugin_marketplaces_as_builtin(tmp_path):
    home = tmp_path / "home"
    keep = make_skill(home / ".claude" / "skills", "keep")
    market = make_skill(
        home / ".claude" / "plugins" / "marketplaces" / "mp" / "plugin" / "skills",
        "market-skill",
    )

    assert sa.discover_skills(home, home=home) == [keep.resolve()]
    assert set(sa.discover_skills(home, include_builtin=True, home=home)) == {
        keep.resolve(), market.resolve(),
    }


def test_plugin_cache_keeps_only_the_newest_version(tmp_path):
    home = tmp_path / "home"
    cache = home / ".claude" / "plugins" / "cache" / "market" / "plug"
    old = make_skill(cache / "1.0.0" / "skills", "old-skill")
    new = make_skill(cache / "2.0.0" / "skills", "new-skill")
    other = make_skill(
        home / ".claude" / "plugins" / "cache" / "market" / "other" / "9.9.9" / "skills",
        "other-skill",
    )
    os.utime(cache / "1.0.0", (1_000_000_000, 1_000_000_000))
    os.utime(cache / "2.0.0", (2_000_000_000, 2_000_000_000))

    expected = sorted({new.resolve(), other.resolve()})
    assert sa.discover_skills(home, home=home) == expected
    assert sa.discover_skills(home, include_builtin=True, home=home) == expected


def test_plugin_cache_prefers_higher_version_over_newer_mtime(tmp_path):
    home = tmp_path / "home"
    cache = home / ".claude" / "plugins" / "cache" / "market" / "plug"
    newer_version = make_skill(cache / "7.0.0" / "skills", "seven")
    newer_mtime = make_skill(cache / "6.4.1" / "skills", "six")
    os.utime(cache / "7.0.0", (1_000_000_000, 1_000_000_000))
    os.utime(cache / "6.4.1", (2_000_000_000, 2_000_000_000))

    assert sa.discover_skills(home, home=home) == [newer_version.resolve()]
    assert newer_mtime.resolve() not in sa.discover_skills(home, home=home)


def test_plugin_cache_falls_back_to_mtime_for_unparseable_versions(tmp_path):
    home = tmp_path / "home"
    cache = home / ".claude" / "plugins" / "cache" / "market" / "plug"
    old = make_skill(cache / "build-aaa" / "skills", "old-skill")
    new = make_skill(cache / "build-bbb" / "skills", "new-skill")
    os.utime(cache / "build-aaa", (1_000_000_000, 1_000_000_000))
    os.utime(cache / "build-bbb", (2_000_000_000, 2_000_000_000))

    assert sa.discover_skills(home, home=home) == [new.resolve()]
    assert old.resolve() not in sa.discover_skills(home, home=home)


def test_parse_version_fallback_without_packaging(monkeypatch):
    monkeypatch.setattr(sa, "_PackagingVersion", None)
    assert sa._parse_version("7.0.0") > sa._parse_version("6.4.1")
    assert sa._parse_version("deadbeef") is None


def test_symlink_to_always_pruned_tree_is_skipped(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    vendor = make_skill(home / ".local" / "lib" / "pkg", "vendor-skill")
    (home / "vendor-link").symlink_to(vendor, target_is_directory=True)

    assert sa.discover_skills(home, home=home) == []


def test_symlink_into_tmp_tree_is_skipped(tmp_path):
    home = tmp_path / "home"
    root = home / "root"
    root.mkdir(parents=True)
    target = make_skill(home / "outside" / "tmp" / "pkg", "tmp-skill")
    (root / "tmp-link").symlink_to(target, target_is_directory=True)

    assert sa.discover_skills(root, home=home) == []


def test_discovery_symlinks_included_resolved_and_deduped(tmp_path):
    root = tmp_path / "root"
    real = make_skill(root, "real")
    (root / "alias").symlink_to(real, target_is_directory=True)

    external = make_skill(tmp_path / "external", "external-skill")
    (root / "external-link").symlink_to(external, target_is_directory=True)

    # A symlink to a directory that is not itself a skill dir is not descended into.
    container = tmp_path / "container"
    make_skill(container, "nested")
    (root / "container-link").symlink_to(container, target_is_directory=True)

    found = sa.discover_skills(root)
    assert found == sorted({real.resolve(), external.resolve()})
    assert (container / "nested").resolve() not in found


def test_discovery_survives_stat_permission_errors(tmp_path, monkeypatch):
    root = tmp_path / "root"
    keep = make_skill(root, "keep")
    locked = tmp_path / "locked"
    locked.mkdir()
    (root / "locked-link").symlink_to(locked, target_is_directory=True)

    real_is_file = Path.is_file

    def guarded(self):
        if self.parent.name == "locked":
            raise PermissionError(13, "denied")
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", guarded)
    assert sa.discover_skills(root) == [keep.resolve()]


def test_discovery_accepts_root_skill_dir_and_skill_md(tmp_path):
    root = tmp_path / "root"
    skill = make_skill(root, "one")
    other = make_skill(root, "two")

    assert sa.discover_skills(root) == sorted([skill.resolve(), other.resolve()])
    assert sa.discover_skills(skill) == [skill.resolve()]
    assert sa.discover_skills(skill / "SKILL.md") == [skill.resolve()]

    lower = root / "lower"
    lower.mkdir()
    (lower / "skill.md").write_text("x", encoding="utf-8")
    assert sa.discover_skills(lower) == [lower.resolve()]

    assert sa.discover_skills(tmp_path / "missing") == []


def test_family_labels(tmp_path):
    home = tmp_path / "home"
    mapping = {
        ".claude": "claude", ".hermes": "hermes", ".codex": "codex",
        ".gemini": "gemini", ".cursor": "cursor", ".qwen": "qwen", ".agents": "agents",
        ".other": "other",
    }
    for hidden, expected in mapping.items():
        path = home / hidden / "skills" / "x"
        path.mkdir(parents=True)
        assert sa.family_label(path, home) == expected

    assert sa.family_label(tmp_path / "elsewhere" / "x", home) == "other"


def test_skill_slug_is_sanitized(tmp_path):
    home = tmp_path / "home"
    path = home / ".claude" / "skills" / "a b"
    path.mkdir(parents=True)
    assert sa.skill_slug(path, home) == "claude__skills__a-b"


# ---------------------------------------------------------------------------
# Report parsing / aggregation
# ---------------------------------------------------------------------------

def test_parse_real_fixture_report():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = sa.parse_report(data, Path("/home/u/.claude/skills/evil-skill"))

    assert report.name == "evil-skill"
    assert report.score == 100
    assert report.severity == "critical"
    assert report.recommendation == "DO_NOT_INSTALL"
    assert report.counts() == {"critical": 0, "high": 2, "medium": 2, "low": 0}
    assert report.worst() == "high"
    assert {f.rule_id for f in report.findings} == {"SC2", "PE3", "LP3", "AST4"}
    first = report.findings[0]
    assert first.severity == "high"
    assert first.file == "SKILL.md"
    assert "curl" in first.message
    assert "curl" in sa.top_finding(report, "medium")
    assert sa.top_finding(report, "critical") == "—"


def test_report_counts_and_top_finding_respect_min_severity():
    report = make_report(findings=[
        sa.Finding("low", "L1", "low thing", "a.md"),
        sa.Finding("high", "H1", "high thing", "b.md"),
        sa.Finding("medium", "M1", "medium thing", "c.md"),
    ])
    assert report.counts() == {"critical": 0, "high": 1, "medium": 1, "low": 1}
    assert report.counts("high") == {"critical": 0, "high": 1, "medium": 0, "low": 0}
    assert sa.top_finding(report, "medium") == "[H1] high thing"
    assert sa.top_finding(report, "high") == "[H1] high thing"


def test_should_fail_thresholds():
    high = make_report(findings=[sa.Finding("high", "H1", "m")])
    medium = make_report(findings=[sa.Finding("medium", "M1", "m")])
    clean = make_report()

    assert sa.should_fail([high], "high")
    assert not sa.should_fail([high], "critical")
    assert sa.should_fail([medium], "medium")
    assert not sa.should_fail([medium], "high")
    assert not sa.should_fail([high], "none")
    assert not sa.should_fail([clean], "low")


# ---------------------------------------------------------------------------
# Scan orchestration
# ---------------------------------------------------------------------------

def test_scan_skill_parses_report_and_passes_flags(tmp_path, monkeypatch):
    skill = make_skill(tmp_path, "evil-skill")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        out = Path(command[command.index("--output") + 1])
        out.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        # SkillSpector exits 1 when findings exist; the report is still valid.
        return subprocess.CompletedProcess(command, 1, "", "findings")

    monkeypatch.setattr(sa.subprocess, "run", fake_run)

    report = sa.scan_skill("skillspector", skill, tmp_path / "out", llm=False, timeout=7)
    assert report.ok
    assert report.score == 100
    assert report.recommendation == "DO_NOT_INSTALL"

    command, kwargs = calls[0]
    assert command[:3] == ["skillspector", "scan", str(skill)]
    assert "--no-llm" in command
    assert command[command.index("--format") + 1] == "json"
    assert kwargs["timeout"] == 7
    assert kwargs["env"] is None
    assert (tmp_path / "out").is_dir()


def test_scan_skill_sets_provider_only_with_llm(tmp_path, monkeypatch):
    skill = make_skill(tmp_path, "demo")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        out = Path(command[command.index("--output") + 1])
        out.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(sa.subprocess, "run", fake_run)

    sa.scan_skill("skillspector", skill, tmp_path / "out", llm=True,
                  provider="openai", timeout=30)
    command, kwargs = calls[0]
    assert "--no-llm" not in command
    assert kwargs["env"]["SKILLSPECTOR_PROVIDER"] == "openai"


def test_scan_skill_timeout_and_failure_become_error_rows(tmp_path, monkeypatch):
    skill = make_skill(tmp_path, "broken")

    def timeout_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(sa.subprocess, "run", timeout_run)
    report = sa.scan_skill("skillspector", skill, tmp_path / "out", timeout=5)
    assert not report.ok
    assert "timed out" in report.error

    def fail_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, "", "something exploded\n")

    monkeypatch.setattr(sa.subprocess, "run", fail_run)
    report = sa.scan_skill("skillspector", skill, tmp_path / "out2", timeout=5)
    assert not report.ok
    assert "exited 2" in report.error
    assert "something exploded" in report.error


def test_scan_skill_does_not_reuse_a_stale_report(tmp_path, monkeypatch):
    skill = make_skill(tmp_path, "demo")
    out = tmp_path / "out"
    out.mkdir()
    (out / f"{sa.skill_slug(skill)}.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    def fail_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, "", "boom")

    monkeypatch.setattr(sa.subprocess, "run", fail_run)
    report = sa.scan_skill("skillspector", skill, out)
    assert not report.ok
    assert "exited 2" in report.error


def test_scan_all_isolates_a_failing_skill(tmp_path):
    good = make_skill(tmp_path, "good")
    bad = make_skill(tmp_path, "bad")
    seen = []

    def scanner(skill):
        seen.append(skill)
        if skill.name == "bad":
            raise RuntimeError("boom")
        return sa.SkillReport(path=skill, name=skill.name)

    reports = sa.scan_all([good, bad], scanner, workers=2)
    assert sorted(seen) == sorted([good, bad])
    assert len(reports) == 2
    errors = [r for r in reports if not r.ok]
    assert len(errors) == 1
    assert "boom" in errors[0].error


# ---------------------------------------------------------------------------
# Output payloads
# ---------------------------------------------------------------------------

def test_summary_payload_sorted_worst_first_and_errors_last():
    reports = [
        make_report("safe", score=0),
        make_report("bad", score=90, severity="critical", recommendation="DO_NOT_INSTALL",
                    findings=[sa.Finding("high", "H1", "bad | thing")]),
        make_report("broken", error="timed out"),
    ]

    payload = sa.summary_payload(reports, Path("/home/u"))
    assert payload["totals"] == {
        "scanned": 2,
        "errors": 1,
        "by_recommendation": {"DO_NOT_INSTALL": 1, "SAFE": 1},
    }
    assert [s["name"] for s in payload["skills"]] == ["bad", "safe", "broken"]

    markdown = sa.render_markdown(reports, Path("/home/u"), "medium", "2026-01-01T00:00:00")
    assert markdown.startswith("# Skill audit")
    assert "| bad | claude | 90 |" in markdown
    assert "bad \\| thing" in markdown
    assert "ERROR" in markdown
    assert "Scanned: 2 skill(s), 1 error(s)" in markdown


def test_display_labels_disambiguate_duplicate_names():
    first = make_report("dup")
    first.path = Path("/home/u/.claude/skills/one/dup")
    second = make_report("dup")
    second.path = Path("/home/u/.claude/skills/two/dup")

    labels = sa.display_labels([first, second])
    assert labels[first.path] != labels[second.path]
    assert labels[first.path].startswith("dup (")


def test_json_format_stdout_contains_only_the_payload(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from jarvis.main import app as cli_app

    skill = make_skill(tmp_path, "demo")
    output = tmp_path / "out"

    def fake_scan(executable, skill_path, output_dir, **kwargs):
        return sa.SkillReport(path=skill_path, name=skill_path.name,
                              score=0, recommendation="SAFE")

    monkeypatch.setattr(sa, "ensure_skillspector", lambda console: "skillspector")
    monkeypatch.setattr(sa, "scan_skill", fake_scan)

    result = CliRunner().invoke(cli_app, [
        "sys", "skill-audit", str(skill), "--format", "json",
        "--output", str(output), "--fail-on", "none",
    ])

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"]["scanned"] == 1
    assert payload["skills"][0]["name"] == "demo"
    assert "Scanning" in result.stderr
    assert "Reports:" in result.stderr


def test_scan_command_shape(tmp_path):
    command = sa.scan_command("skillspector", tmp_path / "s", tmp_path / "r.json")
    assert command == [
        "skillspector", "scan", str(tmp_path / "s"), "--no-llm",
        "--format", "json", "--output", str(tmp_path / "r.json"),
    ]
    command = sa.scan_command("skillspector", tmp_path / "s", tmp_path / "r.json", llm=True)
    assert "--no-llm" not in command
