"""Audit agent skills with NVIDIA SkillSpector (`jarvis sys skill-audit`)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import typer

try:
    from packaging.version import Version as _PackagingVersion
except ImportError:  # pragma: no cover - fallback for minimal environments
    _PackagingVersion = None

from jarvis.config import JARVIS_ROOT

SKILLSPECTOR_REPO = "git+https://github.com/NVIDIA/skillspector.git"
SKILLSPECTOR_INSTALL = f"uv tool install {SKILLSPECTOR_REPO}"
INSTALL_TIMEOUT = 600

SKILL_FILENAMES = ("SKILL.md", "skill.md")
PRUNE_DIRS = frozenset({
    "node_modules", ".git", "venv", ".venv", "__pycache__", ".cache", ".npm",
    "snap", "Dropbox", "site-packages", "dist", "build", ".tmp", "tmp",
})
# Home-relative trees that are always skipped, even with --include-builtin.
ALWAYS_PRUNE_HOME_DIRS = (
    (".local", "lib"),
    (".local", "share", "uv"),
    ("orca", "workspaces"),
)
PLUGIN_CACHE_DIR = (".claude", "plugins", "cache")
# Path component sequences identifying vendor/builtin skill trees.
BUILTIN_PATH_RULES = (
    (".vscode", "extensions"),
    (".cursor", "extensions"),
    (".codex", "skills", ".system"),
    (".cursor", "skills-cursor"),
    (".claude", "plugins", "marketplaces"),
)
BUILTIN_COMPONENT = "builtin"

FAMILY_DIRS = {
    ".claude": "claude",
    ".hermes": "hermes",
    ".codex": "codex",
    ".gemini": "gemini",
    ".cursor": "cursor",
    ".qwen": "qwen",
    ".agents": "agents",
}

SEVERITIES = ("critical", "high", "medium", "low")
SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
MIN_SEVERITY_CHOICES = ("low", "medium", "high", "critical")
FAIL_ON_CHOICES = ("none", "low", "medium", "high", "critical")
FORMAT_CHOICES = ("table", "json", "markdown")
_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")


# ---------------------------------------------------------------------------
# Discovery (pure)
# ---------------------------------------------------------------------------

def is_skill_dir(path: Path) -> bool:
    """A skill directory contains a SKILL.md (or skill.md)."""
    for name in SKILL_FILENAMES:
        try:
            if (path / name).is_file():
                return True
        except OSError:
            continue
    return False


def _has_sequence(parts: Sequence[str], sequence: Sequence[str]) -> bool:
    size = len(sequence)
    return any(tuple(parts[i:i + size]) == tuple(sequence)
               for i in range(len(parts) - size + 1))


def is_builtin_path(path: Path) -> bool:
    """True for editor/vendor skill trees that are not user-installed skills."""
    parts = path.parts
    if BUILTIN_COMPONENT in parts:
        return True
    return any(_has_sequence(parts, rule) for rule in BUILTIN_PATH_RULES)


def _is_under(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _always_pruned(path: Path, home: Path) -> bool:
    return any(_is_under(path, home.joinpath(*parts)) for parts in ALWAYS_PRUNE_HOME_DIRS)


def _has_tmp_component(path: Path, base: Optional[Path] = None) -> bool:
    path = Path(path)
    if base is not None:
        try:
            path = path.relative_to(base)
        except ValueError:
            return False
    return any(part in (".tmp", "tmp") for part in path.parts)


def _newest_plugin_cache_versions(skills: Sequence[Path], home: Path) -> List[Path]:
    """Keep only the newest cache/<marketplace>/<plugin>/<version>/ tree per plugin."""
    cache_root = home.joinpath(*PLUGIN_CACHE_DIR)
    groups: Dict[tuple, Dict[str, List[Path]]] = {}
    passthrough: List[Path] = []
    for skill in skills:
        try:
            parts = skill.relative_to(cache_root).parts
        except ValueError:
            passthrough.append(skill)
            continue
        if len(parts) < 3:
            passthrough.append(skill)
            continue
        marketplace, plugin, version = parts[0], parts[1], parts[2]
        groups.setdefault((marketplace, plugin), {}).setdefault(version, []).append(skill)

    kept = list(passthrough)
    for (marketplace, plugin), versions in groups.items():
        def modified(version: str) -> float:
            directory = cache_root / marketplace / plugin / version
            try:
                return directory.stat().st_mtime
            except OSError:
                return 0.0

        parsed = {version: _parse_version(version) for version in versions}
        if all(value is not None for value in parsed.values()):
            newest = max(versions, key=lambda v: (parsed[v], modified(v), v))
        else:
            newest = max(versions, key=lambda v: (modified(v), v))
        kept.extend(versions[newest])
    return sorted(kept)


def _parse_version(value: str):
    """Comparable version, or None when the directory name is not version-like."""
    value = value.strip()
    if _PackagingVersion is not None:
        try:
            return _PackagingVersion(value)
        except (ValueError, TypeError):
            return None
    match = _VERSION_RE.match(value)
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def discover_skills(root: Path, include_builtin: bool = False,
                    home: Optional[Path] = None) -> List[Path]:
    """Find skill dirs under `root`, a skill dir, or a SKILL.md file.

    Symlinked directories are not descended into, but a symlink that points at a
    skill dir is included via its resolved path. Results are deduped by resolve().
    Installed plugin versions under ~/.claude/plugins/cache are collapsed to the
    newest version per plugin.
    """
    home = Path(home or Path.home()).expanduser().resolve()
    root = Path(root).expanduser()
    try:
        if root.is_file():
            if root.name.lower() != "skill.md":
                return []
            root = root.parent
        root = root.resolve()
        if not root.is_dir():
            return []
    except OSError:
        return []

    if is_skill_dir(root):
        return [root] if include_builtin or not is_builtin_path(root) else []

    found: Dict[Path, Path] = {}
    for dirpath, dirnames, _ in os.walk(root, followlinks=False):
        current = Path(dirpath)
        keep = []
        for name in dirnames:
            child = current / name
            if name in PRUNE_DIRS or _always_pruned(child, home):
                continue
            if child.is_symlink():
                try:
                    target = child.resolve()
                    if target.is_dir() and is_skill_dir(target):
                        if (_has_tmp_component(target, home)
                                or _always_pruned(target, home)
                                or (not include_builtin and is_builtin_path(target))):
                            continue
                        found[target] = target
                except OSError:
                    continue
                continue
            if not include_builtin and is_builtin_path(child):
                continue
            keep.append(name)
        dirnames[:] = keep

        resolved = current.resolve()
        if is_skill_dir(current) and (include_builtin or not is_builtin_path(resolved)):
            found[resolved] = resolved

    return _newest_plugin_cache_versions(sorted(found), home)


def family_label(path: Path, home: Optional[Path] = None) -> str:
    """claude/hermes/codex/... from the first hidden dir under home, else `other`."""
    home = Path(home or Path.home()).expanduser().resolve()
    try:
        relative = Path(path).resolve().relative_to(home)
    except ValueError:
        return "other"
    for part in relative.parts:
        if part.startswith(".") and part not in (".", ".."):
            return FAMILY_DIRS.get(part, "other")
    return "other"


def skill_slug(skill: Path, home: Optional[Path] = None) -> str:
    """Filesystem-safe report name derived from the skill path relative to home."""
    home = Path(home or Path.home()).expanduser().resolve()
    try:
        relative = Path(skill).resolve().relative_to(home)
    except ValueError:
        relative = Path(str(Path(skill).resolve()).lstrip(os.sep))
    slug = "__".join(relative.parts)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-.") or "skill"
    # Sanitizing can map distinct paths to one name; the hash keeps reports apart.
    digest = hashlib.sha1(str(Path(skill).resolve()).encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


# ---------------------------------------------------------------------------
# Report parsing and aggregation (pure)
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    severity: str
    rule_id: str
    message: str
    file: Optional[str] = None


@dataclass
class SkillReport:
    path: Path
    name: str
    family: str = "other"
    score: int = 0
    severity: str = "none"
    recommendation: str = "UNKNOWN"
    findings: List[Finding] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def counts(self, min_severity: str = "low") -> Dict[str, int]:
        threshold = severity_rank(min_severity)
        return {sev: sum(1 for f in self.findings
                         if f.severity == sev and severity_rank(sev) >= threshold)
                for sev in SEVERITIES}

    def worst(self) -> str:
        return max((f.severity for f in self.findings),
                   key=lambda sev: SEVERITY_RANK.get(sev, 0), default="none")


def severity_rank(severity: str) -> int:
    return SEVERITY_RANK.get(str(severity).strip().lower(), 0)


def parse_report(data: dict, skill_path: Path) -> SkillReport:
    """Build a SkillReport from one SkillSpector JSON report."""
    skill = data.get("skill") or {}
    risk = data.get("risk_assessment") or {}
    findings = []
    for issue in data.get("issues") or []:
        location = issue.get("location") or {}
        findings.append(Finding(
            severity=str(issue.get("severity") or "low").strip().lower(),
            rule_id=str(issue.get("id") or issue.get("pattern") or "unknown"),
            message=str(issue.get("finding") or issue.get("pattern")
                        or issue.get("explanation") or "").strip(),
            file=location.get("file"),
        ))
    try:
        score = int(risk.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    return SkillReport(
        path=Path(skill_path).resolve(),
        name=str(skill.get("name") or Path(skill_path).name),
        score=score,
        severity=str(risk.get("severity") or "none").strip().lower(),
        recommendation=str(risk.get("recommendation") or "UNKNOWN").strip().upper(),
        findings=findings,
    )


def visible_findings(report: SkillReport, min_severity: str = "medium") -> List[Finding]:
    threshold = severity_rank(min_severity)
    return [f for f in report.findings if severity_rank(f.severity) >= threshold]


def top_finding(report: SkillReport, min_severity: str = "medium") -> str:
    findings = visible_findings(report, min_severity)
    if not findings:
        return "—"
    best = max(findings, key=lambda f: SEVERITY_RANK.get(f.severity, 0))
    label = f"[{best.rule_id}] " if best.rule_id else ""
    return f"{label}{best.message}"


def should_fail(reports: Sequence[SkillReport], fail_on: str = "high") -> bool:
    if fail_on == "none":
        return False
    # Fail closed: an unscanned skill or a DO_NOT_INSTALL verdict is never a pass.
    threshold = severity_rank(fail_on)
    return any(not report.ok
               or report.recommendation in ("DO_NOT_INSTALL", "DO NOT INSTALL")
               or any(severity_rank(f.severity) >= threshold for f in report.findings)
               for report in reports)


def sort_reports(reports: Sequence[SkillReport]) -> List[SkillReport]:
    """Worst first; error rows at the bottom."""
    return sorted(reports, key=lambda r: (not r.ok, -r.score,
                                          -severity_rank(r.severity), str(r.path)))


def recommendation_totals(reports: Sequence[SkillReport]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for report in reports:
        if report.ok:
            totals[report.recommendation] = totals.get(report.recommendation, 0) + 1
    return dict(sorted(totals.items()))


def shorten(text: str, width: int = 70) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def display_labels(reports: Sequence[SkillReport]) -> Dict[Path, str]:
    """Disambiguate identical skill names by appending a short parent label."""
    counts: Dict[str, int] = {}
    for report in reports:
        counts[report.name] = counts.get(report.name, 0) + 1
    labels: Dict[Path, str] = {}
    used = set()
    for report in sorted(reports, key=lambda r: str(r.path)):
        label = report.name
        if counts[report.name] > 1:
            parent = report.path.parent.name or str(report.path.parent)
            label = f"{report.name} ({shorten(parent, 22)})"
            if label in used:
                digest = hashlib.sha1(str(report.path).encode("utf-8")).hexdigest()[:6]
                label = f"{report.name} ({shorten(parent, 14)}:{digest})"
        used.add(label)
        labels[report.path] = label
    return labels


def summary_payload(reports: Sequence[SkillReport], root: Path,
                    generated_at: Optional[str] = None) -> dict:
    ordered = sort_reports(reports)
    errors = sum(1 for report in reports if not report.ok)
    return {
        "root": str(Path(root).expanduser().resolve()),
        "generated_at": generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "totals": {
            "scanned": len(reports) - errors,
            "errors": errors,
            "by_recommendation": recommendation_totals(reports),
        },
        "skills": [{
            "name": report.name,
            "path": str(report.path),
            "family": report.family,
            "score": report.score,
            "severity": report.severity,
            "recommendation": report.recommendation,
            "counts": report.counts(),
            "findings": [asdict(finding) for finding in report.findings],
            "error": report.error,
        } for report in ordered],
    }


def _md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(reports: Sequence[SkillReport], root: Path, min_severity: str = "medium",
                    generated_at: Optional[str] = None) -> str:
    payload = summary_payload(reports, root, generated_at)
    labels = display_labels(reports)
    totals = payload["totals"]
    lines = [
        "# Skill audit",
        "",
        f"- Root: `{payload['root']}`",
        f"- Generated: {payload['generated_at']}",
        f"- Scanned: {totals['scanned']} skill(s), {totals['errors']} error(s)",
    ]
    if totals["by_recommendation"]:
        counts = ", ".join(f"{name} {count}"
                           for name, count in totals["by_recommendation"].items())
        lines.append(f"- Recommendations: {counts}")
    lines += [
        "",
        "| Skill | Family | Score | Recommendation | Crit | High | Med | Low | Top finding |",
        "|---|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for report in sort_reports(reports):
        if not report.ok:
            lines.append(f"| {_md_cell(labels[report.path])} | {_md_cell(report.family)} | - | ERROR "
                         f"| - | - | - | - | {_md_cell(report.error)} |")
            continue
        counts = report.counts(min_severity)
        lines.append(
            f"| {_md_cell(labels[report.path])} | {_md_cell(report.family)} | {report.score} "
            f"| {_md_cell(report.recommendation)} | {counts['critical']} | {counts['high']} "
            f"| {counts['medium']} | {counts['low']} "
            f"| {_md_cell(shorten(top_finding(report, min_severity), 90))} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_command(executable: str, skill: Path, output_file: Path, llm: bool = False) -> List[str]:
    command = [executable, "scan", str(skill)]
    if not llm:
        command.append("--no-llm")
    command += ["--format", "json", "--output", str(output_file)]
    return command


def _error_report(skill: Path, message: str) -> SkillReport:
    return SkillReport(
        path=Path(skill).resolve(),
        name=Path(skill).name,
        recommendation="ERROR",
        error=message,
    )


def scan_skill(executable: str, skill: Path, output_dir: Path, llm: bool = False,
               provider: str = "claude_cli", timeout: int = 120) -> SkillReport:
    """Run SkillSpector on one skill; never raises — failures become error rows."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{skill_slug(skill)}.json"
    try:
        output_file.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        return _error_report(skill, f"cannot prepare report file: {exc}")
    env = {**os.environ, "SKILLSPECTOR_PROVIDER": provider} if llm else None
    command = scan_command(executable, skill, output_file, llm=llm)

    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return _error_report(skill, f"timed out after {timeout}s")
    except OSError as exc:
        return _error_report(skill, f"could not run skillspector: {exc}")

    if output_file.is_file():
        try:
            data = json.loads(output_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _error_report(skill, f"unreadable report: {exc}")
        if data.get("execution_successful") is False:
            return _error_report(skill, "skillspector reported an unsuccessful scan")
        return parse_report(data, skill)

    # A non-zero exit is normal when findings exist, so only report it when no
    # JSON report was produced at all.
    detail = (proc.stderr or proc.stdout or "").strip()
    last_line = detail.splitlines()[-1] if detail else "no report produced"
    return _error_report(skill, f"skillspector exited {proc.returncode}: {shorten(last_line, 120)}")


def scan_all(skills: Sequence[Path], scanner: Callable[[Path], SkillReport],
             workers: int = 8, on_done: Optional[Callable[[SkillReport], None]] = None
             ) -> List[SkillReport]:
    """Scan skills concurrently. One failing skill never aborts the audit."""
    skills = list(skills)
    if not skills:
        return []
    reports: List[SkillReport] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(skills)))) as pool:
        futures = {pool.submit(scanner, skill): skill for skill in skills}
        for future in as_completed(futures):
            try:
                report = future.result()
            except Exception as exc:  # noqa: BLE001 - one bad skill must not stop the audit
                report = _error_report(futures[future], f"scan failed: {exc}")
            reports.append(report)
            if on_done is not None:
                on_done(report)
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _choice(value: str, allowed: Sequence[str], option: str, console) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        console.print(f"[red]❌ Invalid --{option} '{value}' "
                      f"(choose from: {', '.join(allowed)})[/red]")
        raise typer.Exit(1)
    return normalized


def ensure_skillspector(console) -> str:
    """Return a skillspector path, installing it with uv when missing."""
    found = shutil.which("skillspector")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "skillspector"
    if local.is_file():
        return str(local)

    if shutil.which("uv") is None:
        console.print("[red]❌ `skillspector` is not installed and `uv` is not available.[/red]")
        console.print(f"Install it manually: [cyan]{SKILLSPECTOR_INSTALL}[/cyan]")
        raise typer.Exit(1)

    console.print("[yellow]🔎 SkillSpector not found — installing it (one-time setup)…[/yellow]")
    console.print(f"[dim]$ {SKILLSPECTOR_INSTALL}[/dim]")
    proc = None
    try:
        proc = subprocess.run(["uv", "tool", "install", SKILLSPECTOR_REPO],
                              capture_output=True, text=True, timeout=INSTALL_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as exc:
        console.print(f"[dim]{exc}[/dim]")

    found = shutil.which("skillspector")
    if not found and local.is_file():
        found = str(local)
    if not found:
        console.print("[red]❌ SkillSpector install failed.[/red]")
        if proc is not None and (proc.stderr or "").strip():
            console.print(f"[dim]{proc.stderr.strip().splitlines()[-1]}[/dim]")
        console.print(f"Install it manually: [cyan]{SKILLSPECTOR_INSTALL}[/cyan]")
        raise typer.Exit(1)

    console.print("[green]✅ SkillSpector installed.[/green]")
    return found


def _print_table(console, reports: Sequence[SkillReport], min_severity: str) -> None:
    from rich.markup import escape
    from rich.table import Table

    table = Table(title="Skill audit", header_style="bold")
    table.add_column("Skill", style="cyan")
    table.add_column("Family")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("C/H/M/L", justify="center")
    table.add_column("Top finding", overflow="fold")
    styles = {
        "SAFE": "green",
        "REVIEW": "yellow",
        "CAUTION": "yellow",
        "DO_NOT_INSTALL": "red",
        "DO NOT INSTALL": "red",
    }
    labels = display_labels(reports)
    for report in sort_reports(reports):
        if not report.ok:
            table.add_row(escape(labels[report.path]), escape(report.family), "-",
                          "[red]ERROR[/red]", "-",
                          f"[red]{escape(shorten(report.error or '', 80))}[/red]")
            continue
        counts = report.counts(min_severity)
        style = styles.get(report.recommendation, "dim")
        table.add_row(
            escape(labels[report.path]),
            escape(report.family),
            str(report.score),
            f"[{style}]{escape(report.recommendation)}[/{style}]",
            f"{counts['critical']}/{counts['high']}/{counts['medium']}/{counts['low']}",
            escape(shorten(top_finding(report, min_severity), 70)),
        )
    console.print(table)


def _totals_line(reports: Sequence[SkillReport]) -> str:
    errors = sum(1 for report in reports if not report.ok)
    line = f"Scanned {len(reports) - errors} skill(s), {errors} error(s)"
    counts = recommendation_totals(reports)
    if counts:
        line += " — " + " · ".join(f"{name} {count}" for name, count in counts.items())
    return line


def skill_audit(
    path: Optional[Path] = typer.Argument(
        None, help="Root dir, skill dir, or SKILL.md file to audit (default: ~)"),
    llm: bool = typer.Option(
        False, "--llm/--no-llm", help="Enable LLM analysis (default: static analysis only)"),
    provider: str = typer.Option(
        "claude_cli", "--provider", help="SKILLSPECTOR_PROVIDER value used with --llm"),
    workers: int = typer.Option(
        8, "--workers", min=1, help="Concurrent SkillSpector subprocesses"),
    min_severity: str = typer.Option(
        "medium", "--min-severity", help="low|medium|high|critical — hide findings below this"),
    fmt: str = typer.Option(
        "table", "--format", help="table|json|markdown"),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Report dir (default: ~/.jarvis/reports/skill-audit-<timestamp>)"),
    include_builtin: bool = typer.Option(
        False, "--include-builtin", help="Also scan editor/vendor builtin skill trees"),
    fail_on: str = typer.Option(
        "high", "--fail-on", help="Exit 1 on a finding at/above this severity (none disables)"),
    timeout: int = typer.Option(
        120, "--timeout", min=1, help="Per-skill timeout in seconds"),
):
    """Audit agent skills for security issues with NVIDIA SkillSpector."""
    from rich.console import Console
    from rich.progress import (BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
                               TextColumn, TimeElapsedColumn)

    console = Console()
    min_severity = _choice(min_severity, MIN_SEVERITY_CHOICES, "min-severity", console)
    fail_on = _choice(fail_on, FAIL_ON_CHOICES, "fail-on", console)
    fmt = _choice(fmt, FORMAT_CHOICES, "format", console)
    if fmt != "table":
        console = Console(stderr=True)

    root = (path or Path.home()).expanduser()
    if not root.exists():
        console.print(f"[red]❌ Path not found: {root}[/red]")
        raise typer.Exit(1)

    skills = discover_skills(root, include_builtin=include_builtin)
    if not skills:
        console.print(f"[yellow]⚠️  No skill directories found under {root}[/yellow]")
        if not include_builtin:
            console.print("[dim]Vendor/builtin trees are skipped by default; try --include-builtin.[/dim]")
        raise typer.Exit(1)

    executable = ensure_skillspector(console)
    report_dir = (output.expanduser() if output else
                  JARVIS_ROOT / "reports" / f"skill-audit-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    report_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"🔎 Scanning {len(skills)} skill(s) under {root} "
                  f"({workers} worker(s), {'LLM' if llm else 'static'} analysis)")
    scanner = lambda skill: scan_skill(  # noqa: E731
        executable, skill, report_dir, llm=llm, provider=provider, timeout=timeout)
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as progress:
        task = progress.add_task("Scanning skills", total=len(skills))

        def on_done(report: SkillReport) -> None:
            progress.update(task, advance=1,
                            description=f"Scanned {shorten(report.name, 32)}")

        reports = scan_all(skills, scanner, workers=workers, on_done=on_done)

    for report in reports:
        report.family = family_label(report.path)

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = summary_payload(reports, root, generated_at)
    markdown = render_markdown(reports, root, min_severity, generated_at)
    (report_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (report_dir / "summary.md").write_text(markdown, encoding="utf-8")

    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
    elif fmt == "markdown":
        typer.echo(markdown)
    else:
        _print_table(console, reports, min_severity)
        console.print(_totals_line(reports))

    console.print(f"\n📁 Reports: [cyan]{report_dir}[/cyan]")

    if should_fail(reports, fail_on):
        raise typer.Exit(1)
