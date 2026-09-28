#!/usr/bin/env python3
"""Unit tests for split_commits.py. Run: python3 -m unittest scripts/test_split_commits.py -v"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "split_commits.py"

BASE = "".join(f"line{n}\n" for n in range(1, 31))


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"{' '.join(cmd)} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc


def split(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run([sys.executable, str(SCRIPT), *args], cwd, check=check)


def make_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    run(["git", "init", "-q", "-b", "main"], repo)
    run(["git", "config", "user.email", "t@example.com"], repo)
    run(["git", "config", "user.name", "Test"], repo)
    (repo / "pkg.yaml").write_text(BASE)
    run(["git", "add", "pkg.yaml"], repo)
    run(["git", "commit", "-q", "-m", "chore: base"], repo)
    return repo


def apply_mixed_edit(repo: Path) -> str:
    """Working-tree edit with four independent changes tangled into one file.

    HEAD numbering: line1..line30.
      A  insert alpha1, alpha2 after line3          (pure insertion, 2 lines)
      B  insert beta and gamma after line10          (one hunk, two unrelated lines)
      C  move line15, line16 to after line20         (deletion + insertion, same text)
      D  change line25 -> line25-changed             (modification)
    """
    lines = BASE.splitlines(keepends=True)
    out: list[str] = []
    for n, line in enumerate(lines, 1):
        if n in (15, 16):
            continue
        out.append(line)
        if n == 3:
            out += ["alpha1\n", "alpha2\n"]
        if n == 10:
            out += ["beta\n", "gamma\n"]
        if n == 20:
            out += ["line15\n", "line16\n"]
    text = "".join(out).replace("line25\n", "line25-changed\n")
    (repo / "pkg.yaml").write_text(text)
    return text


def write_plan(repo: Path, commits: list[dict]) -> Path:
    plan = repo.parent / "plan.json"
    plan.write_text(json.dumps({"commits": commits}))
    return plan


def log_subjects(repo: Path) -> list[str]:
    return run(["git", "log", "--format=%s"], repo).stdout.split("\n")[:-1]


def show(repo: Path, rev: str) -> str:
    return run(["git", "show", "--format=", "-U0", rev], repo).stdout


def added_lines(repo: Path, rev: str) -> list[str]:
    return [l[1:] for l in show(repo, rev).splitlines() if l.startswith("+") and not l.startswith("+++")]


class InspectTests(unittest.TestCase):
    def test_lists_numbered_hunks_with_both_line_numberings(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            out = split(repo, "inspect", "--context", "0").stdout
            self.assertIn("pkg.yaml  (5 hunks)", out)
            self.assertIn("H1   +4-5", out)
            self.assertIn("H2   +13-14", out)
            self.assertIn("H3   -15-16", out)
            self.assertIn("H4   +23-24", out)
            self.assertIn("H5   +29 -25", out)
            self.assertIn("13 + beta", out)
            self.assertIn("15 - line15", out)

    def test_reports_untracked_files_as_whole_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / "new.txt").write_text("hi\n")
            out = split(repo, "inspect").stdout
            self.assertIn("?? new.txt", out)


class ApplyTests(unittest.TestCase):
    def test_splits_one_file_into_atomic_commits_and_leaves_tree_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            final = apply_mixed_edit(repo)
            plan = write_plan(repo, [
                {"message": "chore(pkg): add alpha", "changes": [{"path": "pkg.yaml", "hunks": ["H1"]}]},
                {"message": "chore(pkg): add beta", "changes": [{"path": "pkg.yaml", "new": ["13"]}]},
                {"message": "chore(pkg): add gamma", "changes": [{"path": "pkg.yaml", "new": ["14"]}]},
                {"message": "chore(pkg): move lines 15-16 after 20",
                 "changes": [{"path": "pkg.yaml", "hunks": ["H3", "H4"]}]},
                {"message": "fix(pkg): change line25\n\nWith a body.",
                 "changes": [{"path": "pkg.yaml", "hunks": ["H5"]}]},
            ])
            out = split(repo, "apply", str(plan)).stdout
            self.assertIn("Created 5 commits on main", out)
            self.assertIn("HEAD now matches the working tree", out)
            self.assertEqual(log_subjects(repo), [
                "fix(pkg): change line25", "chore(pkg): move lines 15-16 after 20",
                "chore(pkg): add gamma", "chore(pkg): add beta", "chore(pkg): add alpha", "chore: base",
            ])
            self.assertEqual(run(["git", "status", "--porcelain"], repo).stdout, "")
            self.assertEqual((repo / "pkg.yaml").read_text(), final)
            self.assertEqual(added_lines(repo, "HEAD~4"), ["alpha1", "alpha2"])
            beta = show(repo, "HEAD~3")
            self.assertIn("+beta", beta)
            self.assertNotIn("gamma", beta)
            move = show(repo, "HEAD~1")
            self.assertIn("-line15", move)
            self.assertIn("+line15", move)
            body = run(["git", "log", "-1", "--format=%b"], repo).stdout.strip()
            self.assertEqual(body, "With a body.")

    def test_whole_file_changes_and_multi_file_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            (repo / "config.toml").write_text("x = 1\n")
            plan = write_plan(repo, [
                {"message": "feat(tool): add tool", "changes": [
                    {"path": "pkg.yaml", "hunks": ["H1"]},
                    {"path": "config.toml", "whole": True},
                ]},
                {"message": "chore(pkg): the rest", "changes": [{"path": "pkg.yaml", "hunks": ["H2", "H3", "H4", "H5"]}]},
            ])
            split(repo, "apply", str(plan))
            files = run(["git", "show", "--format=", "--name-only", "HEAD~1"], repo).stdout.split()
            self.assertEqual(sorted(files), ["config.toml", "pkg.yaml"])
            self.assertEqual(run(["git", "status", "--porcelain"], repo).stdout, "")

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            plan = write_plan(repo, [{"message": "all", "changes": [
                {"path": "pkg.yaml", "hunks": ["H1", "H2", "H3", "H4", "H5"]}]}])
            out = split(repo, "apply", "--dry-run", str(plan)).stdout
            self.assertIn("Dry run: 1 commit", out)
            self.assertIn("+ alpha1", out)
            self.assertEqual(log_subjects(repo), ["chore: base"])

    def test_rejects_unassigned_lines_unless_allow_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            plan = write_plan(repo, [{"message": "only alpha", "changes": [{"path": "pkg.yaml", "hunks": ["H1"]}]}])
            proc = split(repo, "apply", str(plan), check=False)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("unassigned changes remain", proc.stderr)
            self.assertEqual(log_subjects(repo), ["chore: base"])
            out = split(repo, "apply", "--allow-partial", str(plan)).stdout
            self.assertIn("Left uncommitted on purpose", out)
            self.assertEqual(len(log_subjects(repo)), 2)
            self.assertNotEqual(run(["git", "status", "--porcelain"], repo).stdout, "")

    def test_rejects_overlapping_selections(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            plan = write_plan(repo, [
                {"message": "a", "changes": [{"path": "pkg.yaml", "hunks": ["H1"]}]},
                {"message": "b", "changes": [{"path": "pkg.yaml", "new": ["4"], "hunks": ["H2", "H3", "H4", "H5"]}]},
            ])
            proc = split(repo, "apply", str(plan), check=False)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("assigned twice", proc.stderr)

    def test_rejects_lines_that_are_not_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            plan = write_plan(repo, [{"message": "a", "changes": [{"path": "pkg.yaml", "new": ["1"]}]}])
            proc = split(repo, "apply", str(plan), check=False)
            self.assertIn("not added lines", proc.stderr)

    def test_refuses_to_run_with_a_dirty_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            (repo / "other.txt").write_text("staged\n")
            run(["git", "add", "other.txt"], repo)
            plan = write_plan(repo, [{"message": "a", "changes": [{"path": "pkg.yaml", "hunks": ["H1"]}]}])
            proc = split(repo, "apply", str(plan), check=False)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("already has staged changes", proc.stderr)

    def test_runs_from_a_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            sub = repo / "sub"
            sub.mkdir()
            plan = write_plan(repo, [{"message": "all", "changes": [
                {"path": "pkg.yaml", "hunks": ["H1", "H2", "H3", "H4", "H5"]}]}])
            out = split(sub, "apply", str(plan)).stdout
            self.assertIn("Created 1 commit", out)


class EdgeCaseTests(unittest.TestCase):
    def test_stages_working_tree_mode_change_on_hunk_split_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            (repo / "pkg.yaml").chmod(0o755)
            plan = write_plan(repo, [{"message": "all", "changes": [
                {"path": "pkg.yaml", "hunks": ["H1", "H2", "H3", "H4", "H5"]}]}])
            out = split(repo, "apply", str(plan)).stdout
            self.assertIn("HEAD now matches the working tree", out)
            mode = run(["git", "ls-tree", "HEAD", "pkg.yaml"], repo).stdout.split()[0]
            self.assertEqual(mode, "100755")
            self.assertEqual(run(["git", "status", "--porcelain"], repo).stdout, "")

    def test_lone_carriage_return_and_missing_trailing_newline_keep_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            base = b"a\rb\n" + b"c\n" + b"d"          # lone CR inside line 1, no newline at EOF
            (repo / "odd.txt").write_bytes(base)
            run(["git", "add", "odd.txt"], repo)
            run(["git", "commit", "-q", "-m", "chore: odd"], repo)
            final = b"a\rb\n" + b"NEW\n" + b"c\n" + b"d\n" + b"e"   # insert after line 1; add newline to d; add e
            (repo / "odd.txt").write_bytes(final)
            out = split(repo, "inspect", "--context", "0").stdout
            self.assertIn("H1   +2", out)
            plan = write_plan(repo, [
                {"message": "one", "changes": [{"path": "odd.txt", "hunks": ["H1"]}]},
                {"message": "two", "changes": [{"path": "odd.txt", "hunks": ["H2"]}]},
            ])
            split(repo, "apply", str(plan))
            self.assertEqual(run(["git", "status", "--porcelain"], repo).stdout, "")
            self.assertEqual((repo / "odd.txt").read_bytes(), final)
            first = subprocess.run(["git", "show", "HEAD~1:odd.txt"], cwd=repo, capture_output=True, check=True).stdout
            self.assertEqual(first, b"a\rb\nNEW\nc\nd")  # bytes: text mode would translate the lone CR

    def test_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / "my dir").mkdir()
            (repo / "my dir" / "some file.txt").write_text("one\n")
            run(["git", "add", "my dir/some file.txt"], repo)
            run(["git", "commit", "-q", "-m", "chore: spaces"], repo)
            (repo / "my dir" / "some file.txt").write_text("one\ntwo\n")
            out = split(repo, "inspect", "--context", "0").stdout
            self.assertIn("my dir/some file.txt  (1 hunk)", out)
            plan = write_plan(repo, [{"message": "spaces", "changes": [{"path": "my dir/some file.txt", "hunks": ["H1"]}]}])
            split(repo, "apply", str(plan))
            self.assertEqual(run(["git", "status", "--porcelain"], repo).stdout, "")

    def test_deleted_path_selected_by_hunk_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / "pkg.yaml").unlink()
            plan = write_plan(repo, [{"message": "x", "changes": [{"path": "pkg.yaml", "hunks": ["H1"]}]}])
            proc = split(repo, "apply", str(plan), check=False)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("missing from the working tree", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_inspect_does_not_list_a_staged_modification_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            apply_mixed_edit(repo)
            run(["git", "add", "pkg.yaml"], repo)
            out = split(repo, "inspect", "--context", "0").stdout
            self.assertIn("pkg.yaml  (5 hunks)", out)
            self.assertNotIn("Other changes", out)

    def test_warns_when_ignore_rules_skip_files_under_a_whole_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            (repo / ".gitignore").write_text("*.patch\n")
            run(["git", "add", ".gitignore"], repo)
            run(["git", "commit", "-q", "-m", "chore: ignore patches"], repo)
            (repo / "skill").mkdir()
            (repo / "skill" / "SKILL.md").write_text("hi\n")
            (repo / "skill" / "fixture.patch").write_text("diff\n")
            (repo / "skill-workspace").mkdir()
            (repo / "skill-workspace" / "scratch.patch").write_text("not ours\n")  # sibling sharing the prefix
            plan = write_plan(repo, [{"message": "feat: skill", "changes": [{"path": "skill", "whole": True}]}])
            out = split(repo, "apply", str(plan)).stdout
            self.assertIn("WARNING: ignore rules kept these files out", out)
            self.assertIn("skill/fixture.patch", out)
            self.assertNotIn("skill-workspace", out)
            files = run(["git", "show", "--format=", "--name-only", "HEAD"], repo).stdout.split()
            self.assertEqual(files, ["skill/SKILL.md"])


if __name__ == "__main__":
    unittest.main()
