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
