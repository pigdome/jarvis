"""Unit tests for the CLAUDE.md merge logic of `jarvis sys orca` (no Orca / npx needed).

Run: venv/bin/python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jarvis.commands import orca  # noqa: E402

TEMPLATE = (Path(__file__).resolve().parent.parent / "config" / "orca" / orca.TEMPLATE_NAME).read_text()
BLOCK = orca.render(TEMPLATE, ["agy", "codex", "qwen"], "git diff, `pytest`")

ALPA_LIKE = """# CLAUDE.md

Intro text.

## Orca orchestration (multi-agent)

- dev: Qwen — general dev/agent: `worker-start --agent qwen --worktree new-child --name <short-name>`

## Testing rules

- Use Playwright.
"""


class RenderTest(unittest.TestCase):
    def test_hash_in_marker_and_placeholders_filled(self):
        self.assertRegex(BLOCK.splitlines()[0], r"v1 sha=[0-9a-f]{12} start")
        self.assertNotIn("{role_lines}", BLOCK)
        self.assertIn("(git diff, `pytest`)", BLOCK)
        self.assertIn("Orca id `qwen-code`", BLOCK)
        self.assertFalse(orca.find_managed(BLOCK + "\n").edited)

    def test_split_right_rule(self):
        self.assertIn('terminal split --terminal "$ORCA_TERMINAL_HANDLE" --direction vertical', BLOCK)
        self.assertIn("worker-start --task <id> --worktree current --terminal <handle>", BLOCK)
        self.assertIn("--terminal <last-worker-handle> --direction horizontal", BLOCK)
        self.assertNotIn("Only AGY works in the current worktree", BLOCK)

    def test_agents_subset(self):
        block = orca.render(TEMPLATE, orca.parse_agents("agy,claude"), "x")
        self.assertIn("dev: AGY", block)
        self.assertIn("dev: Claude sub-agent", block)
        self.assertNotIn("dev: Codex", block)
        self.assertNotIn("dev: Qwen", block)

    def test_unknown_agent(self):
        with self.assertRaises(ValueError):
            orca.parse_agents("agy,gemini")


class MergeTest(unittest.TestCase):
    def test_create(self):
        r = orca.merge(None, BLOCK)
        self.assertEqual(r.state, "created")
        self.assertEqual(r.content, f"# CLAUDE.md\n\n{BLOCK}\n")

    def test_idempotent(self):
        first = orca.merge(None, BLOCK).content
        r = orca.merge(first, BLOCK)
        self.assertEqual(r.state, "up-to-date")
        self.assertFalse(r.changed)
        self.assertEqual(r.content, first)

    def test_second_merge_is_noop_from_every_state(self):
        edited = orca.merge(None, BLOCK).content.replace("always.", "now.")
        starts = [None, "", "# x\n", "# x", "# CLAUDE.md\n\nA.\n\n## Testing rules\n\n- t\n", ALPA_LIKE, edited]
        for start in starts:
            for force in (False, True):
                once = orca.merge(start, BLOCK, force=True).content
                again = orca.merge(once, BLOCK, force=force)
                self.assertEqual(again.state, "up-to-date", (start, force))
                self.assertEqual(again.content, once)
                self.assertEqual(orca.unmerge(orca.unmerge(once).content).state, "absent")

    def test_append(self):
        r = orca.merge("# CLAUDE.md\n\nSome rules.\n", BLOCK)
        self.assertEqual(r.state, "appended")
        self.assertEqual(r.content, f"# CLAUDE.md\n\nSome rules.\n\n{BLOCK}\n")

    def test_insert_before_testing_rules(self):
        orig = "# CLAUDE.md\n\nA.\n\n## Testing rules\n\n- t\n"
        r = orca.merge(orig, BLOCK)
        self.assertEqual(r.state, "inserted")
        self.assertEqual(r.content, f"# CLAUDE.md\n\nA.\n\n{BLOCK}\n\n## Testing rules\n\n- t\n")
        self.assertEqual(r.content.count("jarvis:orca-orchestration end"), 1)

    def test_replace_when_template_changes(self):
        old = orca.merge(None, orca.render(TEMPLATE, ["agy"], "x")).content
        r = orca.merge(old, BLOCK)
        self.assertEqual(r.state, "replaced")
        self.assertEqual(r.content, f"# CLAUDE.md\n\n{BLOCK}\n")

    def test_edited_skipped_without_force(self):
        content = orca.merge(None, BLOCK).content.replace("Plan first, always.", "Plan first!")
        r = orca.merge(content, BLOCK)
        self.assertEqual(r.state, "edited")
        self.assertEqual(r.content, content)
        r = orca.merge(content, BLOCK, force=True)
        self.assertEqual(r.state, "replaced")
        self.assertEqual(r.content, f"# CLAUDE.md\n\n{BLOCK}\n")

    def test_legacy(self):
        r = orca.merge(ALPA_LIKE, BLOCK)
        self.assertEqual(r.state, "legacy")
        self.assertEqual(r.content, ALPA_LIKE)
        r = orca.merge(ALPA_LIKE, BLOCK, force=True)
        self.assertEqual(r.state, "replaced")
        self.assertIn("Orca id `qwen-code`", r.content)
        self.assertNotIn("--agent qwen ", r.content)
        self.assertTrue(r.content.startswith("# CLAUDE.md\n\nIntro text.\n\n<!-- jarvis:orca-orchestration"))
        self.assertTrue(r.content.endswith(f"{BLOCK}\n\n## Testing rules\n\n- Use Playwright.\n"))


class StateTest(unittest.TestCase):
    def test_states(self):
        self.assertEqual(orca.section_state(None, BLOCK), "missing")
        self.assertEqual(orca.section_state("# x\n", BLOCK), "missing")
        fresh = orca.merge(None, BLOCK).content
        self.assertEqual(orca.section_state(fresh, BLOCK), "up-to-date")
        self.assertEqual(orca.section_state(fresh.replace("always.", "now."), BLOCK), "edited")
        self.assertEqual(orca.section_state(orca.merge(None, orca.render(TEMPLATE, ["agy"], "x")).content, BLOCK), "outdated")
        self.assertEqual(orca.section_state(ALPA_LIKE, BLOCK), "legacy")


class UnmergeTest(unittest.TestCase):
    def roundtrip(self, orig):
        merged = orca.merge(orig, BLOCK).content
        r = orca.unmerge(merged)
        self.assertEqual(r.state, "removed")
        return r.content

    def test_remove_appended(self):
        orig = "# CLAUDE.md\n\nSome rules.\n"
        self.assertEqual(self.roundtrip(orig), orig)

    def test_remove_inserted(self):
        orig = "# CLAUDE.md\n\nA.\n\n## Testing rules\n\n- t\n"
        self.assertEqual(self.roundtrip(orig), orig)

    def test_remove_created(self):
        self.assertEqual(orca.unmerge(orca.merge(None, BLOCK).content).content, "# CLAUDE.md\n")

    def test_remove_absent_edited_legacy(self):
        self.assertEqual(orca.unmerge("# x\n").state, "absent")
        edited = orca.merge(None, BLOCK).content.replace("always.", "now.")
        self.assertEqual(orca.unmerge(edited).state, "edited")
        self.assertEqual(orca.unmerge(edited, force=True).content, "# CLAUDE.md\n")
        self.assertEqual(orca.unmerge(ALPA_LIKE).state, "legacy")
        self.assertEqual(orca.unmerge(ALPA_LIKE, force=True).content,
                         "# CLAUDE.md\n\nIntro text.\n\n## Testing rules\n\n- Use Playwright.\n")


class VerifyTest(unittest.TestCase):
    def test_detect(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.assertEqual(orca.detect_verify(p), "git diff, the project's tests")
            (p / "package.json").write_text("{}")
            self.assertEqual(orca.detect_verify(p), "git diff, `npm test`")
            (p / "pyproject.toml").write_text("")
            self.assertEqual(orca.detect_verify(p), "git diff, `pytest`")
            (p / "pubspec.yaml").write_text("")
            self.assertEqual(orca.detect_verify(p), "git diff, `flutter analyze`, tests")


if __name__ == "__main__":
    unittest.main()
