# Spec: `jarvis sys orca` — Orca multi-agent orchestration setup

**Status:** Draft · **Date:** 2026-10-04 · **Owner:** apirak

## 1. Goal

One command that turns any project into an Orca orchestration project, the same setup that was done by hand in `/srv/punsarn/alpa`:

- Claude is the **main** agent (coordinator and senior dev). It plans with the user and dispatches work.
- AGY (Antigravity) is the **main dev**; Codex and Qwen are **general devs**.
- Every worker opens in a **split pane right of Claude** (the first splits Claude's pane `--direction vertical`, later ones stack below the last worker with `horizontal`), then is handed over with `worker-start --worktree current --terminal <handle>`. `worker-start` has no placement flag, and split panes always belong to Claude's worktree (`terminal_worktree_mismatch`), so all workers share the current worktree with disjoint file ownership. A child worktree (own tab) is the fallback when tasks can't be split by file.
- **No worker starts until the user approves the plan.**

```
 YOU ⇄ CLAUDE (plan)  ──"approved"──▶  CLAUDE (coordinator)
                                         ├─▶ AGY    (split pane, right)
                                         ├─▶ Codex  (split pane, right, below AGY)
                                         └─▶ Qwen   (split pane, right, below Codex)
                                    ◀── worker_done / questions ──┘
```

## 2. Background: what the manual setup was

Only two things are needed per project, and both stay inside the project. Nothing goes in `~/`.

1. **Orca skills, installed locally:**
   ```bash
   orca-ide skills install --skill orchestration --skill orca-cli --local --agent claude-code
   ```
   This creates `.claude/skills/orchestration/`, `.claude/skills/orca-cli/` and `skills-lock.json`.
2. **Rules section in the project's `CLAUDE.md`.** It covers plan-first, the roles, the CLI name, the task-spec format and verification.

Host gotcha: plain `orca` on this machine is the **GNOME screen reader**. The Orca IDE CLI is `orca-ide`, also at `/opt/Orca/resources/bin/orca-ide`.

## 3. Commands

New Typer group `orca` under `sys` (`src/jarvis/commands/orca.py`, registered with `system.app.add_typer(orca.app, name="orca")`):

| Command | Description |
|---|---|
| `jarvis sys orca setup [PATH...]` | Install skills and the CLAUDE.md section into one or more projects (default: cwd) |
| `jarvis sys orca status [PATH...]` | Show per project: skills installed? section present? section up to date? |
| `jarvis sys orca remove [PATH...]` | Remove the section and the two skill dirs. Leaves `skills-lock.json` unless `--purge` is passed |

### `setup` options

| Option | Default | Meaning |
|---|---|---|
| `--all-orca-repos` | off | Use every repo from `orca-ide repo list` as the PATH list |
| `--agents TEXT` | `agy,codex,qwen` | Which dev roles go into the section (comma list). Claude main is always on |
| `--verify TEXT` | auto | Verification command line for the section (see §5.3) |
| `--skip-skills` | off | Only write CLAUDE.md |
| `--skip-claude-md` | off | Only install skills |
| `--force` | off | Overwrite a section that was edited by hand (see §5.2) |
| `--dry-run` | off | Print what would change (planned commands and a diff of CLAUDE.md) and write nothing |

## 4. Bundled assets

```
config/orca/
  CLAUDE-orchestration.md   # section template with {placeholders}
```

Find it the same way `sys claude-skill` finds `config/claude-skills` (`system.py:494`): `BUNDLE_DIR/config/orca`, then next to the binary, then `~/.jarvis/orca/` as a user override. `jarvis.spec` already bundles `config/`, so no spec change is needed.

### Template (`config/orca/CLAUDE-orchestration.md`)

```markdown
<!-- jarvis:orca-orchestration v1 start — managed by `jarvis sys orca setup`; edit the template, not here -->
## Orca orchestration (multi-agent)

When the user asks to delegate, orchestrate, or split work across agents, use the `orchestration` skill.

- **Plan first, always.** Discuss the plan with the user before starting any worker: task split, which agent owns each task, which worktree, and how each task is verified done. Iterate until the user explicitly says "approved". Do NOT run `orchestration run-create` or `worker-start` before that.
- **Roles:**
  - main: Claude (this pane) — main + senior dev; controls every agent. Plans, dispatches, answers worker questions, reviews, verifies, reports. Takes over any task that stalls.
{role_lines}
  - Every dev works in the current worktree, in its own split pane right of Claude (see "New worker panes" below). Their file ownership must not overlap.
  - Claude owns the outcome, verifies every worker's "done" claim against the repo, and finishes stalled work itself.
- **New worker panes open split right.** Start every worker in a split pane, never a new tab. Claude stays on the left; workers stack in the right column:
  1. Open the pane. The first worker splits Claude's pane to the right: `orca-ide terminal split --terminal "$ORCA_TERMINAL_HANDLE" --direction vertical --command <agent-cli> --json`. Each later worker splits the last worker's pane below it: `--terminal <last-worker-handle> --direction horizontal`. Note `result.split.handle`.
  2. `orca-ide terminal wait --terminal <handle> --for tui-idle --timeout-ms 60000`
  3. `orca-ide orchestration worker-start --task <id> --worktree current --terminal <handle>`
  - Agent CLIs: AGY `agy`, Codex `codex`, Qwen `qwen`, Claude `claude`. `--model`/`--effort` can't be combined with `--terminal`, so pass model flags inside `--command`.
  - Split panes always belong to Claude's worktree (Orca rejects a mismatch with `terminal_worktree_mismatch`). If two tasks can't be given disjoint files, run one of them in its own child worktree instead: `worker-start --agent <orca-id> --worktree new-child --name <short-name>` (opens in that worktree's tab). Claude then merges its branch after review.
- **CLI:** plain `orca` on this host is the GNOME screen reader. Use `orca-ide` (`/opt/Orca/resources/bin/orca-ide`) as the executable everywhere the skill says `ORCA`.
- Give each task spec Target / Change / Constraints / Ownership / Acceptance (see the skill). Two workers must never edit the same files.
- Before reporting done, verify every worker's result yourself ({verify}).
<!-- jarvis:orca-orchestration end -->
```

`{role_lines}` is built from `--agents`:

| Key | Line |
|---|---|
| `agy` | `  - dev: AGY — main dev/agent (CLI \`agy\`, Orca id \`antigravity\`)` |
| `codex` | `  - dev: Codex — general dev/agent (CLI \`codex\`, Orca id \`codex\`)` |
| `qwen` | `  - dev: Qwen — general dev/agent (CLI \`qwen\`, Orca id \`qwen-code\`)` |
| `claude` | `  - dev: Claude sub-agent — isolated work (CLI \`claude\`, Orca id \`claude\`)` |

> Note: the Orca agent id for Qwen is **`qwen-code`**, not `qwen`. alpa's hand-written section has `--agent qwen`, and that's a bug.

## 5. Behaviour

### 5.1 Pre-flight (once per run)
1. Resolve the Orca CLI: `orca-ide` on PATH, else `/opt/Orca/resources/bin/orca-ide`. If neither is found, print an error and exit 1. **Never** call bare `orca`.
2. `orca-ide status`. If the runtime is unreachable, print a warning and continue, because skill install works offline from the bundled registry.
3. Check that `npx` exists (needed for the skill install). If it's missing and skills weren't skipped, print an error and exit 1.

### 5.2 Per project
1. If PATH is not a directory, print `✗ <path>: not found`, continue with the next one, and make the final exit code 1.
2. **Skills:** run `orca-ide skills install --skill orchestration --skill orca-cli --local --agent claude-code` with `cwd=PATH`. Stream the output only when `--verbose` is set. Success means both `.claude/skills/orchestration/SKILL.md` and `.claude/skills/orca-cli/SKILL.md` exist afterwards.
3. **CLAUDE.md**, idempotent:
   - Render the template.
   - If `CLAUDE.md` is missing, create it as `# CLAUDE.md\n\n` plus the section.
   - If the **managed markers** are present, replace the text between them. If the existing block differs from the last rendered version (the user edited it by hand), skip with a warning unless `--force` is passed. Detect this by storing a hash of the rendered block in the start marker (`v1 sha=<12 hex>`).
   - If there are **no markers but a `## Orca orchestration` heading** (a hand-made legacy section like alpa's), do not touch it. Print `⚠ legacy section found — run with --force to replace` and, with `--force`, replace from that heading up to the next `## ` heading.
   - Otherwise, append the section. If the file contains `## Testing rules`, insert the section before it, to match alpa's layout.
4. Never `git add` or commit. Print the changed files so the user can review them.

### 5.3 `{verify}` auto-detection
Use the first match:
- `pubspec.yaml` → `git diff, \`flutter analyze\`, tests`
- `pyproject.toml` / `requirements.txt` → `git diff, \`pytest\``
- `package.json` → `git diff, \`npm test\``
- none of these → `git diff, the project's tests`

`--verify` overrides the detected value.

### 5.4 Output (Rich, matching jarvis style)
```
🤖 Orca orchestration setup
  ✓ /srv/punsarn/starkcode    skills ✓  CLAUDE.md + section (inserted before "## Testing rules")
  ⏺ /srv/punsarn/veronica     skills ✓  CLAUDE.md up to date
  ⚠ /srv/punsarn/alpa         skills ✓  legacy section — skipped (use --force)
  ✗ /srv/punsarn/nope         not found

Next: open a NEW Claude pane in each project (skills load at session start).
```

## 6. Out of scope
- Global (`~/.claude`) install. Setup is per project only, by design.
- Fixing Qwen session restore in Orca. That's an upstream gap: Orca records no Qwen session IDs, so Qwen panes don't come back after Orca restarts.
- Committing the changes.

## 7. Acceptance
- [ ] `jarvis sys orca setup --dry-run /tmp/x` on a fresh git repo prints the planned commands and a diff, and writes nothing.
- [ ] `jarvis sys orca setup /tmp/x` creates both skill dirs and a `CLAUDE.md` with exactly one managed section. A second run reports "up to date" and leaves the files byte-identical.
- [ ] With an existing `CLAUDE.md` that has `## Testing rules`, the section lands just before that heading and the rest of the file is unchanged.
- [ ] A hand-edited managed block is skipped without `--force` and replaced with it.
- [ ] alpa (legacy section) is skipped by default. With `--force` the section is replaced and the Qwen line uses `qwen-code`.
- [ ] `--agents agy,claude` renders only those role lines.
- [ ] `status` shows the correct state for all three cases: fresh, up to date, and legacy/edited.
- [ ] `remove` restores `CLAUDE.md` to its content without the section.
- [ ] If `orca-ide` is missing, the command exits 1 with a clear message, and bare `orca` is never run.
- [ ] Unit tests for the CLAUDE.md merge logic (create, append, insert-before, replace, legacy, edited, remove) run without Orca or npx.
- [ ] `jarvis help` lists `sys orca setup|status|remove`, and the README has a row for each.
