import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import typer

from jarvis.config import BUNDLE_DIR, CONFIG_DIR, JARVIS_ROOT

app = typer.Typer(
    help="Orca multi-agent orchestration setup (per project)",
    no_args_is_help=True,
)

TEMPLATE_NAME = "CLAUDE-orchestration.md"
ORCA_FALLBACK = Path("/opt/Orca/resources/bin/orca-ide")
SKILLS = ("orchestration", "orca-cli")
DEFAULT_AGENTS = "agy,codex,qwen"
INSTALL_TIMEOUT = 600  # seconds for `orca-ide skills install`

ROLE_LINES = {
    "agy": "  - dev: AGY — main dev/agent (CLI `agy`, Orca id `antigravity`)",
    "codex": "  - dev: Codex — general dev/agent (CLI `codex`, Orca id `codex`)",
    "qwen": "  - dev: Qwen — general dev/agent (CLI `qwen`, Orca id `qwen-code`)",
    "claude": "  - dev: Claude sub-agent — isolated work (CLI `claude`, Orca id `claude`)",
}

START_RE = re.compile(r"^<!-- jarvis:orca-orchestration v(\d+)(?: sha=([0-9a-f]{12}))? start.*?-->[ \t]*$", re.M)
END_RE = re.compile(r"^<!-- jarvis:orca-orchestration end -->[ \t]*$", re.M)
LEGACY_RE = re.compile(r"^## Orca orchestration\b.*$", re.M)
TESTING_RE = re.compile(r"^## Testing rules\b", re.M)
NEXT_H2_RE = re.compile(r"^## ", re.M)


# ---------------------------------------------------------------------------
# Pure CLAUDE.md logic (no Orca / npx needed — unit tested)
# ---------------------------------------------------------------------------

def parse_agents(agents: str) -> List[str]:
    keys = [a.strip().lower() for a in agents.split(",") if a.strip()]
    unknown = [k for k in keys if k not in ROLE_LINES]
    if unknown:
        raise ValueError(f"unknown agent(s): {', '.join(unknown)} (valid: {', '.join(ROLE_LINES)})")
    return list(dict.fromkeys(keys))


def detect_verify(project: Path) -> str:
    if (project / "pubspec.yaml").exists():
        return "git diff, `flutter analyze`, tests"
    if (project / "pyproject.toml").exists() or (project / "requirements.txt").exists():
        return "git diff, `pytest`"
    if (project / "package.json").exists():
        return "git diff, `npm test`"
    return "git diff, the project's tests"


def _sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def _split_block(block: str):
    """Return (start_line, body, end_line) of a block; body excludes the marker lines."""
    lines = block.rstrip("\n").split("\n")
    return lines[0], "\n".join(lines[1:-1]), lines[-1]


def render(template: str, agents: List[str], verify: str) -> str:
    """Render the template into a managed block (no trailing newline) with the body hash in the start marker."""
    text = template.replace("{role_lines}", "\n".join(ROLE_LINES[a] for a in agents)).replace("{verify}", verify)
    start, body, end = _split_block(text)
    start = re.sub(r" start\b", f" sha={_sha(body)} start", start, count=1)
    return f"{start}\n{body}\n{end}"


@dataclass
class Managed:
    start: int      # offset of the start marker
    end: int        # offset just past the end marker line (incl. its newline)
    block: str      # the block text without trailing newline
    sha: Optional[str]

    @property
    def edited(self) -> bool:
        _, body, _ = _split_block(self.block)
        return self.sha is None or _sha(body) != self.sha


def find_managed(content: str) -> Optional[Managed]:
    m = START_RE.search(content)
    if not m:
        return None
    e = END_RE.search(content, m.end())
    if not e:
        return None
    end = e.end() + (1 if content[e.end():e.end() + 1] == "\n" else 0)
    return Managed(m.start(), end, content[m.start():e.end()], m.group(2))


def find_legacy(content: str):
    """Span (start, end) of a hand-made '## Orca orchestration' section, up to the next '## ' heading."""
    m = LEGACY_RE.search(content)
    if not m:
        return None
    n = NEXT_H2_RE.search(content, m.end())
    return m.start(), (n.start() if n else len(content))


@dataclass
class MergeResult:
    content: str
    state: str      # created | appended | inserted | replaced | up-to-date | edited | legacy
    changed: bool


def merge(content: Optional[str], block: str, force: bool = False) -> MergeResult:
    if content is None:
        return MergeResult(f"# CLAUDE.md\n\n{block}\n", "created", True)

    managed = find_managed(content)
    if managed:
        if managed.block == block:
            return MergeResult(content, "up-to-date", False)
        if managed.edited and not force:
            return MergeResult(content, "edited", False)
        new = content[:managed.start] + block + "\n" + content[managed.end:]
        return MergeResult(new, "replaced", True)

    legacy = find_legacy(content)
    if legacy:
        if not force:
            return MergeResult(content, "legacy", False)
        s, e = legacy
        tail = content[e:]
        new = content[:s] + block + ("\n\n" if tail else "\n") + tail
        return MergeResult(new, "replaced", True)

    t = TESTING_RE.search(content)
    if t:
        new = content[:t.start()] + block + "\n\n" + content[t.start():]
        return MergeResult(new, "inserted", True)

    base = content if content.endswith("\n") or not content else content + "\n"
    return MergeResult(base + ("\n" if base else "") + block + "\n", "appended", True)


def unmerge(content: str, force: bool = False) -> MergeResult:
    """Remove the managed section (or a legacy one with --force), restoring the surrounding text."""
    managed = find_managed(content)
    if managed:
        if managed.edited and not force:
            return MergeResult(content, "edited", False)
        span = (managed.start, managed.end)
    else:
        legacy = find_legacy(content)
        if not legacy:
            return MergeResult(content, "absent", False)
        if not force:
            return MergeResult(content, "legacy", False)
        span = legacy

    head, tail = content[:span[0]].rstrip("\n"), content[span[1]:].lstrip("\n")
    if not tail.strip():
        new = head + "\n" if head.strip() else ""
    else:
        # Rejoin with the single blank line that merge() puts between sections.
        new = head + "\n\n" + tail if head else tail
    return MergeResult(new, "removed", True)


def section_state(content: Optional[str], block: str) -> str:
    """missing | up-to-date | outdated | edited | legacy"""
    if content is None:
        return "missing"
    managed = find_managed(content)
    if managed:
        if managed.block == block:
            return "up-to-date"
        return "edited" if managed.edited else "outdated"
    return "legacy" if find_legacy(content) else "missing"


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def find_template() -> Optional[Path]:
    candidates = [
        JARVIS_ROOT / "orca",                             # ~/.jarvis/orca/ (user override)
        CONFIG_DIR / "orca",                              # configured / local config dir
        Path(sys.executable).parent / "config" / "orca",  # next to the binary
        BUNDLE_DIR / "config" / "orca",                  # bundled binary or source tree
    ]
    for d in candidates:
        if (d / TEMPLATE_NAME).exists():
            return d / TEMPLATE_NAME
    return None


def resolve_orca_cli() -> Optional[str]:
    """Never returns bare `orca` — on this host that is the GNOME screen reader."""
    found = shutil.which("orca-ide")
    if found:
        return found
    if ORCA_FALLBACK.exists():
        return str(ORCA_FALLBACK)
    return None


def skills_installed(project: Path) -> bool:
    return all((project / ".claude" / "skills" / s / "SKILL.md").exists() for s in SKILLS)


def install_cmd(orca: str) -> List[str]:
    cmd = [orca, "skills", "install"]
    for s in SKILLS:
        cmd += ["--skill", s]
    return cmd + ["--local", "--agent", "claude-code"]


def orca_repo_paths(orca: str) -> List[Path]:
    out = subprocess.run([orca, "repo", "list", "--json"], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or out.stdout.strip() or "orca-ide repo list failed")
    data = json.loads(out.stdout)
    return [Path(r["path"]) for r in data.get("result", {}).get("repos", []) if r.get("path")]


def _load_template(console) -> str:
    tpl = find_template()
    if tpl is None:
        console.print(f"[red]❌ Template {TEMPLATE_NAME} not found[/red] (looked in bundle, next to binary, {JARVIS_ROOT / 'orca'})")
        raise typer.Exit(1)
    return tpl.read_text(encoding="utf-8")


def _agents_or_exit(agents: str, console) -> List[str]:
    try:
        return parse_agents(agents)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)


def _read(path: Path) -> Optional[str]:
    return path.read_text(encoding="utf-8") if path.exists() else None


def _print_diff(console, path: Path, old: Optional[str], new: str):
    diff = difflib.unified_diff(
        (old or "").splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=str(path) if old is not None else "/dev/null", tofile=str(path),
    )
    for line in diff:
        style = "green" if line.startswith("+") else "red" if line.startswith("-") else "cyan" if line.startswith("@@") else "dim"
        console.print(line.rstrip("\n"), style=style, markup=False, highlight=False, soft_wrap=True)


def _paths(paths: Optional[List[Path]]) -> List[Path]:
    return [p.expanduser().resolve() for p in (paths or [Path.cwd()])]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def setup(
    paths: Optional[List[Path]] = typer.Argument(None, help="Project directories (default: cwd)"),
    all_orca_repos: bool = typer.Option(False, "--all-orca-repos", help="Use every repo from `orca-ide repo list`"),
    agents: str = typer.Option(DEFAULT_AGENTS, "--agents", help="Dev roles for the section (agy,codex,qwen,claude). Claude main is always on"),
    verify: Optional[str] = typer.Option(None, "--verify", help="Verification text for the section (default: auto-detect)"),
    skip_skills: bool = typer.Option(False, "--skip-skills", help="Only write CLAUDE.md"),
    skip_claude_md: bool = typer.Option(False, "--skip-claude-md", help="Only install skills"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite a hand-edited or legacy section"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Print planned commands and CLAUDE.md diff; write nothing"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream skill installer output"),
):
    """
    Install Orca skills + the CLAUDE.md orchestration section into projects.
    """
    from rich.console import Console
    console = Console()

    agent_keys = _agents_or_exit(agents, console)
    template = _load_template(console) if not skip_claude_md else ""

    # Pre-flight
    orca = resolve_orca_cli()
    if orca is None:
        console.print("[red]❌ Orca IDE CLI not found.[/red] Looked for `orca-ide` on PATH and "
                      f"{ORCA_FALLBACK}. (Bare `orca` is the GNOME screen reader and is never used.)")
        raise typer.Exit(1)
    try:
        st = subprocess.run([orca, "status"], capture_output=True, text=True, timeout=15)
        if st.returncode != 0 or "runtimeReachable: true" not in st.stdout:
            console.print("[yellow]⚠ Orca runtime not reachable — continuing (skill install works offline).[/yellow]")
    except (subprocess.TimeoutExpired, OSError):
        console.print("[yellow]⚠ `orca-ide status` failed — continuing (skill install works offline).[/yellow]")
    if not skip_skills and shutil.which("npx") is None:
        console.print("[red]❌ `npx` not found — it is needed for skill install.[/red] Install Node.js or pass --skip-skills.")
        raise typer.Exit(1)

    if all_orca_repos:
        try:
            targets = [p.resolve() for p in orca_repo_paths(orca)] + (_paths(paths) if paths else [])
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
            console.print(f"[red]❌ Could not list Orca repos: {e}[/red]")
            raise typer.Exit(1)
        targets = list(dict.fromkeys(targets))
    else:
        targets = _paths(paths)

    console.print("🤖 [bold]Orca orchestration setup[/bold]" + (" [dim](dry run)[/dim]" if dry_run else ""))
    failed = False
    changed_files: List[Path] = []
    width = max(len(str(t)) for t in targets) if targets else 0

    for project in targets:
        label = str(project).ljust(width)
        if not project.is_dir():
            console.print(f"  [red]✗[/red] {label}  not found")
            failed = True
            continue

        icon, parts = "⏺", []

        # Skills
        if skip_skills:
            pass
        elif dry_run:
            parts.append(f"[dim]would run:[/dim] (cd {project} && {' '.join(install_cmd(orca))})")
        else:
            before = skills_installed(project)
            # The installer clones the whole Orca repo (~440 MB) for two SKILL.md files:
            # show progress, never wait on stdin/credential prompts, and cap the wait.
            env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
            try:
                if verbose:
                    res = subprocess.run(install_cmd(orca), cwd=project, text=True, env=env,
                                         stdin=subprocess.DEVNULL, timeout=INSTALL_TIMEOUT)
                else:
                    with console.status(f"Installing skills in {project.name} "
                                        "(clones github.com/stablyai/orca, ~1 min)…"):
                        res = subprocess.run(install_cmd(orca), cwd=project, text=True, env=env,
                                             stdin=subprocess.DEVNULL, capture_output=True,
                                             timeout=INSTALL_TIMEOUT)
            except subprocess.TimeoutExpired:
                res = subprocess.CompletedProcess(install_cmd(orca), 124, "",
                                                  f"timed out after {INSTALL_TIMEOUT}s (GitHub clone stalled?)")
            if skills_installed(project):
                parts.append("skills ✓")
                if not before:
                    icon = "✓"
                    changed_files += [project / ".claude" / "skills" / s for s in SKILLS]
            else:
                parts.append("[red]skills ✗[/red]")
                icon = "✗"
                failed = True
                if not verbose and res.returncode != 0:
                    err = (res.stderr or res.stdout or "").strip().splitlines()[-3:]
                    parts.append("[dim]" + " | ".join(err) + "[/dim]")

        # CLAUDE.md
        if not skip_claude_md:
            md = project / "CLAUDE.md"
            old = _read(md)
            block = render(template, agent_keys, verify or detect_verify(project))
            result = merge(old, block, force=force)
            msgs = {
                "created": "CLAUDE.md created",
                "appended": "CLAUDE.md + section (appended)",
                "inserted": 'CLAUDE.md + section (inserted before "## Testing rules")',
                "replaced": "CLAUDE.md section replaced",
                "up-to-date": "CLAUDE.md up to date",
                "edited": "[yellow]hand-edited section — skipped (use --force)[/yellow]",
                "legacy": "[yellow]legacy section — skipped (use --force)[/yellow]",
            }
            parts.append(msgs[result.state])
            if result.state in ("edited", "legacy") and icon != "✗":
                icon = "⚠"
            if result.changed:
                if icon == "⏺":
                    icon = "✓"
                if dry_run:
                    console.print(f"  {icon} {label}  " + "  ".join(parts), soft_wrap=True)
                    _print_diff(console, md, old, result.content)
                    continue
                md.write_text(result.content, encoding="utf-8")
                changed_files.append(md)

        colour = {"✓": "green", "⏺": "blue", "⚠": "yellow", "✗": "red"}[icon]
        console.print(f"  [{colour}]{icon}[/{colour}] {label}  " + "  ".join(parts), soft_wrap=True)

    if changed_files and not dry_run:
        console.print("\n[dim]Changed (not committed — review with git diff):[/dim]")
        for f in changed_files:
            console.print(f"  [dim]• {f}[/dim]")
    if not dry_run:
        console.print("\nNext: open a NEW Claude pane in each project (skills load at session start).")
    if failed:
        raise typer.Exit(1)


@app.command()
def status(
    paths: Optional[List[Path]] = typer.Argument(None, help="Project directories (default: cwd)"),
    agents: str = typer.Option(DEFAULT_AGENTS, "--agents", help="Agents to compare the section against"),
    verify: Optional[str] = typer.Option(None, "--verify", help="Verify text to compare against (default: auto-detect)"),
):
    """
    Show per project: skills installed, section present / up to date.
    """
    from rich.console import Console
    from rich.table import Table
    console = Console()

    agent_keys = _agents_or_exit(agents, console)
    template = _load_template(console)

    table = Table(title="Orca orchestration status")
    table.add_column("Project", style="cyan")
    table.add_column("Skills")
    table.add_column("CLAUDE.md section")
    styles = {
        "up-to-date": "[green]✓ up to date[/green]",
        "outdated": "[yellow]outdated (re-run setup)[/yellow]",
        "edited": "[yellow]hand-edited[/yellow]",
        "legacy": "[yellow]legacy (setup --force)[/yellow]",
        "missing": "[red]✗ missing[/red]",
    }
    failed = False
    for project in _paths(paths):
        if not project.is_dir():
            table.add_row(str(project), "[red]not found[/red]", "")
            failed = True
            continue
        block = render(template, agent_keys, verify or detect_verify(project))
        state = section_state(_read(project / "CLAUDE.md"), block)
        table.add_row(str(project), "[green]✓[/green]" if skills_installed(project) else "[red]✗[/red]", styles[state])
    console.print(table)
    if failed:
        raise typer.Exit(1)


@app.command()
def remove(
    paths: Optional[List[Path]] = typer.Argument(None, help="Project directories (default: cwd)"),
    purge: bool = typer.Option(False, "--purge", help="Also drop the two skills from skills-lock.json"),
    force: bool = typer.Option(False, "--force", "-f", help="Also remove a hand-edited or legacy section"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be removed; change nothing"),
):
    """
    Remove the CLAUDE.md section and the Orca skill dirs.
    """
    from rich.console import Console
    console = Console()

    console.print("🤖 [bold]Orca orchestration remove[/bold]" + (" [dim](dry run)[/dim]" if dry_run else ""))
    failed = False
    for project in _paths(paths):
        if not project.is_dir():
            console.print(f"  [red]✗[/red] {project}  not found")
            failed = True
            continue
        parts = []

        md = project / "CLAUDE.md"
        old = _read(md)
        if old is not None:
            result = unmerge(old, force=force)
            parts.append({
                "removed": "section removed",
                "absent": "no section",
                "edited": "[yellow]hand-edited section — kept (use --force)[/yellow]",
                "legacy": "[yellow]legacy section — kept (use --force)[/yellow]",
            }[result.state])
            if result.changed:
                if dry_run:
                    _print_diff(console, md, old, result.content)
                else:
                    md.write_text(result.content, encoding="utf-8")

        removed_skills = [s for s in SKILLS if (project / ".claude" / "skills" / s).exists()]
        if removed_skills:
            parts.append(f"skills removed: {', '.join(removed_skills)}")
            if not dry_run:
                for s in removed_skills:
                    shutil.rmtree(project / ".claude" / "skills" / s)
                for d in (project / ".claude" / "skills", project / ".claude"):
                    if d.is_dir() and not any(d.iterdir()):
                        d.rmdir()

        lock = project / "skills-lock.json"
        if purge and lock.exists():
            data = json.loads(lock.read_text(encoding="utf-8"))
            skills = data.get("skills", {})
            if any(s in skills for s in SKILLS):
                for s in SKILLS:
                    skills.pop(s, None)
                parts.append("skills-lock.json " + ("deleted" if not skills else "purged"))
                if not dry_run:
                    if skills:
                        lock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    else:
                        lock.unlink()

        console.print(f"  ⏺ {project}  " + ("  ".join(parts) or "nothing to remove"), soft_wrap=True)
    if failed:
        raise typer.Exit(1)
