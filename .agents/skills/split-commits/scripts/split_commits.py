#!/usr/bin/env python3
"""Split a mixed working tree into several commits, choosing changes by hunk or by line.

Subcommands
  inspect [PATH ...]                 list changed files and numbered zero-context hunks
  apply PLAN.json [--dry-run] [--allow-partial]
                                     stage and commit each entry of the plan, in order

The working tree is never touched. Each intermediate file state is written straight
into the index (`git hash-object` + `git update-index`), so the file on disk stays
exactly as the user left it and, after the last commit, HEAD matches the working
tree. That final equality is verified and reported.

Plan format (JSON):
{
  "commits": [
    {
      "message": "chore(packages): add gitnr",
      "changes": [
        {"path": ".chezmoidata/packages.yaml", "hunks": ["H4", "H9"]},
        {"path": ".chezmoidata/packages.yaml", "new": ["445-446"], "old": ["441-447"]},
        {"path": "private_dot_config/gitnr/config.toml", "whole": true}
      ]
    }
  ]
}

  hunks  ids printed by `inspect`
  new    added-line numbers in the working-tree file ("12" or "12-15")
  old    deleted-line numbers in HEAD's version of the file
  whole  `git add` the path as-is (untracked, deleted, binary, renamed files)

A path is either selected by hunk/line in one or more commits, or `whole` in exactly
one commit, never both. Every changed line must land in exactly one commit unless
--allow-partial is given, in which case leftovers stay uncommitted in the working tree.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass

HUNK_HEADER = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RANGE = re.compile(r"^(\d+)(?:-(\d+))?$")
DEFAULT_CONTEXT = 2


class SplitError(Exception):
    """A user-facing failure: bad plan, dirty index, git error."""


# --------------------------------------------------------------------------- git


def git(*args: str, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", *args], input=stdin, capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise SplitError(f"git {' '.join(args)} failed ({proc.returncode}): {err}")
    return proc.stdout


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], capture_output=True).returncode == 0


def chdir_to_repo_root() -> str:
    root = git("rev-parse", "--show-toplevel").decode().strip()
    os.chdir(root)
    return root


# ------------------------------------------------------------------------- model


@dataclass(frozen=True)
class Hunk:
    """One zero-context hunk. Counts of 0 mean a pure insertion or pure deletion."""

    id: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    @property
    def old_lines(self) -> range:
        return range(self.old_start, self.old_start + self.old_count)

    @property
    def new_lines(self) -> range:
        return range(self.new_start, self.new_start + self.new_count)

    @property
    def old_lines_before(self) -> int:
        """How many HEAD lines precede this hunk (the unchanged prefix)."""
        return self.old_start - 1 if self.old_count else self.old_start

    def label(self) -> str:
        parts = []
        if self.new_count:
            parts.append(f"+{fmt_range(self.new_lines)}")
        if self.old_count:
            parts.append(f"-{fmt_range(self.old_lines)}")
        return " ".join(parts)


@dataclass(frozen=True)
class FileDiff:
    path: str
    mode: str
    head: tuple[bytes, ...]
    work: tuple[bytes, ...]
    hunks: tuple[Hunk, ...]

    @property
    def added(self) -> frozenset[int]:
        return frozenset(n for h in self.hunks for n in h.new_lines)

    @property
    def deleted(self) -> frozenset[int]:
        return frozenset(n for h in self.hunks for n in h.old_lines)

    def hunk(self, hunk_id: str) -> Hunk:
        for h in self.hunks:
            if h.id == hunk_id:
                return h
        raise SplitError(f"{self.path}: no hunk {hunk_id} (have {', '.join(h.id for h in self.hunks)})")


@dataclass(frozen=True)
class Selection:
    """Cumulative or per-commit choice of lines for one path."""

    new: frozenset[int]
    old: frozenset[int]

    def union(self, other: "Selection") -> "Selection":
        return Selection(self.new | other.new, self.old | other.old)

    def overlaps(self, other: "Selection") -> "Selection":
        return Selection(self.new & other.new, self.old & other.old)

    @property
    def empty(self) -> bool:
        return not self.new and not self.old


EMPTY = Selection(frozenset(), frozenset())


@dataclass(frozen=True)
class PlannedCommit:
    message: str
    partial: dict[str, Selection]
    whole: tuple[str, ...]


# ----------------------------------------------------------------------- reading


def fmt_range(r: range) -> str:
    if len(r) == 1:
        return str(r.start)
    return f"{r.start}-{r.stop - 1}"


def split_lines(blob: bytes) -> tuple[bytes, ...]:
    """Split on LF only, keeping the delimiter, so numbering matches git's hunks."""
    if not blob:
        return ()
    parts = blob.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])  # final line without a trailing newline
    return tuple(lines)


def changed_tracked_paths(paths: list[str]) -> list[str]:
    out = git("diff", "--name-only", "--diff-filter=M", "-z", "HEAD", "--", *paths)
    return [p for p in out.decode().split("\0") if p]


def other_changes(paths: list[str]) -> list[str]:
    """Status lines for things `inspect` can only offer as whole files."""
    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *paths)
    entries = iter(e for e in out.decode().split("\0") if e)
    lines = []
    for entry in entries:
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":
            path = f"{next(entries, '?')} -> {path}"  # rename/copy: the old name follows
        if code in (" M", "M ", "MM"):
            continue  # ordinary modification, handled by hunks
        lines.append(f"{code} {path}")
    return lines


def worktree_mode(path: str, index_mode: str) -> str:
    """The mode `git add` would record: the index mode unless core.fileMode says to trust disk."""
    if os.path.islink(path):
        raise SplitError(f"{path} is a symlink in the working tree; use \"whole\": true")
    if not os.path.isfile(path):
        raise SplitError(f"{path} is missing from the working tree; use \"whole\": true")
    filemode = subprocess.run(["git", "config", "--type=bool", "core.fileMode"], capture_output=True, text=True)
    if filemode.stdout.strip() == "false":
        return index_mode
    return "100755" if os.stat(path).st_mode & 0o111 else "100644"


def read_file_diff(path: str) -> FileDiff:
    ls = git("ls-files", "-s", "--", path).decode().strip()
    if not ls:
        raise SplitError(f"{path} is not tracked in the index; use \"whole\": true")
    mode = worktree_mode(path, ls.split()[0])
    head = split_lines(git("show", f"HEAD:{path}"))
    with open(path, "rb") as fh:
        work = split_lines(fh.read())
    raw = git("diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", path)
    hunks = []
    for line in raw.splitlines():
        m = HUNK_HEADER.match(line)
        if not m:
            continue
        old_start, old_count, new_start, new_count = (
            int(m.group(1)),
            int(m.group(2)) if m.group(2) is not None else 1,
            int(m.group(3)),
            int(m.group(4)) if m.group(4) is not None else 1,
        )
        hunks.append(Hunk(f"H{len(hunks) + 1}", old_start, old_count, new_start, new_count))
    return FileDiff(path, mode, head, work, tuple(hunks))


# ---------------------------------------------------------------------- building


def build_content(fd: FileDiff, sel: Selection) -> bytes:
    """HEAD content plus the selected additions, minus the selected deletions."""
    out: list[bytes] = []
    cursor = 0  # number of HEAD lines already emitted
    for h in fd.hunks:
        out.extend(fd.head[cursor : h.old_lines_before])
        cursor = h.old_lines_before
        for n in h.old_lines:
            if n not in sel.old:
                out.append(fd.head[n - 1])
        cursor += h.old_count
        for n in h.new_lines:
            if n in sel.new:
                out.append(fd.work[n - 1])
    out.extend(fd.head[cursor:])
    return b"".join(out)


def ignored_under(path: str) -> list[str]:
    """Untracked files under `path` that `git add` skipped because an ignore rule matches them."""
    out = git("ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", path)
    prefix = path.rstrip("/") + "/"
    # git matches untracked pathspecs by string prefix, so `skill` also returns `skill-workspace/...`
    return [p for p in out.decode().split("\0") if p and (p == path or p.startswith(prefix))]


def stage_content(fd: FileDiff, content: bytes) -> None:
    sha = git("hash-object", "-w", "--stdin", "--path", fd.path, stdin=content).decode().strip()
    git("update-index", "--add", "--cacheinfo", f"{fd.mode},{sha},{fd.path}")


# ------------------------------------------------------------------------ plans


def parse_ranges(values, what: str, path: str) -> frozenset[int]:
    chosen: set[int] = set()
    for v in values:
        m = RANGE.match(str(v).strip())
        if not m:
            raise SplitError(f"{path}: bad {what} range {v!r}; use \"12\" or \"12-15\"")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if b < a:
            raise SplitError(f"{path}: bad {what} range {v!r}; end before start")
        chosen.update(range(a, b + 1))
    return frozenset(chosen)


def resolve_change(change: dict, diffs: dict[str, FileDiff]) -> tuple[str, Selection | None]:
    path = change.get("path")
    if not path:
        raise SplitError("every change needs a \"path\"")
    if change.get("whole"):
        extra = {k for k in ("hunks", "new", "old") if change.get(k)}
        if extra:
            raise SplitError(f"{path}: \"whole\" cannot be combined with {sorted(extra)}")
        return path, None
    if path not in diffs:
        diffs[path] = read_file_diff(path)
    fd = diffs[path]
    new: set[int] = set()
    old: set[int] = set()
    for hid in change.get("hunks", []):
        h = fd.hunk(str(hid))
        new.update(h.new_lines)
        old.update(h.old_lines)
    new.update(parse_ranges(change.get("new", []), "new", path))
    old.update(parse_ranges(change.get("old", []), "old", path))
    bad_new = sorted(new - fd.added)
    bad_old = sorted(old - fd.deleted)
    if bad_new:
        raise SplitError(f"{path}: new line(s) {bad_new} are not added lines in this diff")
    if bad_old:
        raise SplitError(f"{path}: old line(s) {bad_old} are not deleted lines in this diff")
    if not new and not old:
        raise SplitError(f"{path}: change selects nothing")
    return path, Selection(frozenset(new), frozenset(old))


def load_plan(plan_path: str, diffs: dict[str, FileDiff]) -> list[PlannedCommit]:
    try:
        with open(plan_path, "rb") as fh:
            plan = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SplitError(f"cannot read plan {plan_path}: {exc}") from exc
    entries = plan.get("commits") if isinstance(plan, dict) else None
    if not entries:
        raise SplitError("plan needs a non-empty \"commits\" list")
    commits: list[PlannedCommit] = []
    for i, entry in enumerate(entries, 1):
        message = (entry.get("message") or "").strip()
        if not message:
            raise SplitError(f"commit #{i} has no message")
        partial: dict[str, Selection] = {}
        whole: list[str] = []
        for change in entry.get("changes") or []:
            path, sel = resolve_change(change, diffs)
            if sel is None:
                whole.append(path)
            else:
                partial[path] = partial.get(path, EMPTY).union(sel)
        if not partial and not whole:
            raise SplitError(f"commit #{i} ({message!r}) has no changes")
        commits.append(PlannedCommit(message, partial, tuple(whole)))
    return commits


def validate_plan(commits: list[PlannedCommit], diffs: dict[str, FileDiff], allow_partial: bool) -> None:
    whole_paths: dict[str, int] = {}
    seen: dict[str, Selection] = {}
    for i, c in enumerate(commits, 1):
        for p in c.whole:
            if p in whole_paths:
                raise SplitError(f"{p}: marked whole in commits #{whole_paths[p]} and #{i}")
            whole_paths[p] = i
        for p, sel in c.partial.items():
            dup = seen.get(p, EMPTY).overlaps(sel)
            if not dup.empty:
                raise SplitError(
                    f"{p}: lines assigned twice (commit #{i} re-selects "
                    f"+{sorted(dup.new)} -{sorted(dup.old)})"
                )
            seen[p] = seen.get(p, EMPTY).union(sel)
    both = set(whole_paths) & set(seen)
    if both:
        raise SplitError(f"{sorted(both)}: cannot be both \"whole\" and hunk/line selected")
    if allow_partial:
        return
    for p, fd in diffs.items():
        sel = seen.get(p, EMPTY)
        left_new = sorted(fd.added - sel.new)
        left_old = sorted(fd.deleted - sel.old)
        if left_new or left_old:
            raise SplitError(
                f"{p}: unassigned changes remain (+{left_new} -{left_old}). "
                "Add them to a commit or pass --allow-partial."
            )


# ---------------------------------------------------------------------- inspect


def print_hunk(fd: FileDiff, h: Hunk, context: int, out) -> None:
    out.write(f"  {h.id:<4} {h.label()}\n")
    if context:
        before_end = h.new_start if h.new_count else h.new_start + 1
        for n in range(max(1, before_end - context), before_end):
            out.write(f"       {n:>5}   {fd.work[n - 1].decode(errors='replace').rstrip()}\n")
    for n in h.old_lines:
        out.write(f"       {n:>5} - {fd.head[n - 1].decode(errors='replace').rstrip()}\n")
    for n in h.new_lines:
        out.write(f"       {n:>5} + {fd.work[n - 1].decode(errors='replace').rstrip()}\n")
    if context:
        anchor = h.new_start + h.new_count if h.new_count else h.new_start + 1
        for n in range(anchor, min(len(fd.work), anchor + context - 1) + 1):
            out.write(f"       {n:>5}   {fd.work[n - 1].decode(errors='replace').rstrip()}\n")


def cmd_inspect(args) -> int:
    chdir_to_repo_root()
    out = sys.stdout
    paths = changed_tracked_paths(args.paths)
    if not paths and not other_changes(args.paths):
        out.write("Nothing to commit: working tree matches HEAD.\n")
        return 0
    out.write("Zero-context hunks vs HEAD. '+' numbers index the working-tree file, "
              "'-' numbers index HEAD's copy. Unmarked lines are unchanged context.\n")
    for p in paths:
        fd = read_file_diff(p)
        out.write(f"\n{p}  ({len(fd.hunks)} hunk{'s' if len(fd.hunks) != 1 else ''})\n")
        for h in fd.hunks:
            print_hunk(fd, h, args.context, out)
    others = other_changes(args.paths)
    if others:
        out.write("\nOther changes (select with \"whole\": true):\n")
        for line in others:
            out.write(f"  {line}\n")
    return 0


# ------------------------------------------------------------------------ apply


def describe_commit(c: PlannedCommit, diffs: dict[str, FileDiff], out) -> None:
    out.write(f"\n{c.message}\n")
    for p, sel in c.partial.items():
        fd = diffs[p]
        out.write(f"  {p}  (+{len(sel.new)} -{len(sel.old)})\n")
        for h in fd.hunks:
            olds = [n for n in h.old_lines if n in sel.old]
            news = [n for n in h.new_lines if n in sel.new]
            for n in olds:
                out.write(f"       {n:>5} - {fd.head[n - 1].decode(errors='replace').rstrip()}\n")
            for n in news:
                out.write(f"       {n:>5} + {fd.work[n - 1].decode(errors='replace').rstrip()}\n")
    for p in c.whole:
        out.write(f"  {p}  (whole file)\n")


def count_changes(c: PlannedCommit) -> str:
    plus = sum(len(s.new) for s in c.partial.values())
    minus = sum(len(s.old) for s in c.partial.values())
    tail = f", {len(c.whole)} whole file{'s' if len(c.whole) != 1 else ''}" if c.whole else ""
    return f"+{plus} -{minus}{tail}"


def cmd_apply(args) -> int:
    chdir_to_repo_root()
    if not git_ok("rev-parse", "--verify", "-q", "HEAD"):
        raise SplitError("repository has no commits yet; make an initial commit first")
    if not git_ok("diff", "--cached", "--quiet"):
        raise SplitError("the index already has staged changes; `git reset` them (or commit) first "
                         "so each new commit contains only what the plan says")

    diffs: dict[str, FileDiff] = {}
    commits = load_plan(args.plan, diffs)
    for p in changed_tracked_paths([]):
        diffs.setdefault(p, read_file_diff(p))
    validate_plan(commits, diffs, args.allow_partial)

    out = sys.stdout
    if args.dry_run:
        out.write(f"Dry run: {len(commits)} commit{'s' if len(commits) != 1 else ''} would be created.\n")
        for c in commits:
            describe_commit(c, diffs, out)
        return 0

    start = git("rev-parse", "--short", "HEAD").decode().strip()
    done = run_commits(commits, diffs, start)
    if done is None:
        return 1
    return report(commits, done, start, args.allow_partial, out)


def run_commits(commits: list[PlannedCommit], diffs: dict[str, FileDiff], start: str) -> list[tuple[str, PlannedCommit]] | None:
    """Stage and commit each plan entry in order. On any failure, say what landed and how to undo it."""
    cumulative: dict[str, Selection] = {}
    done: list[tuple[str, PlannedCommit]] = []
    try:
        for c in commits:
            for p, sel in c.partial.items():
                cumulative[p] = cumulative.get(p, EMPTY).union(sel)
                stage_content(diffs[p], build_content(diffs[p], cumulative[p]))
            for p in c.whole:
                git("add", "--", p)
            git("commit", "-q", "-F", "-", stdin=c.message.encode() + b"\n")
            done.append((git("rev-parse", "--short", "HEAD").decode().strip(), c))
        return done
    except Exception as exc:  # noqa: BLE001 - any failure here leaves partial commits; the user needs the undo hint
        label = str(exc) if isinstance(exc, SplitError) else f"{type(exc).__name__}: {exc}"
        sys.stderr.write(f"\nerror: {label}\n")
        if done:
            sys.stderr.write(f"{len(done)} commit(s) were created before the failure:\n")
            for sha, c in done:
                sys.stderr.write(f"  {sha}  {c.message.splitlines()[0]}\n")
        sys.stderr.write(f"Working tree is untouched. To undo everything: git reset {start}\n")
        return None


def report(commits: list[PlannedCommit], done: list[tuple[str, PlannedCommit]], start: str, allow_partial: bool, out) -> int:
    branch = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    out.write(f"Created {len(done)} commit{'s' if len(done) != 1 else ''} on {branch} (was {start}):\n")
    for sha, c in done:
        out.write(f"  {sha}  {c.message.splitlines()[0]}  ({count_changes(c)})\n")

    skipped = {p: ignored_under(p) for c in commits for p in c.whole}
    skipped = {p: files for p, files in skipped.items() if files}
    if skipped:
        out.write("\nWARNING: ignore rules kept these files out of their \"whole\" path; "
                  "`git add -f <file>` and amend if they belong in the commit:\n")
        for p, files in skipped.items():
            for f in files:
                out.write(f"  {f}  (under {p}; see `git check-ignore -v {f}`)\n")

    touched = sorted({p for c in commits for p in c.partial} | {p for c in commits for p in c.whole})
    dirty = [p for p in touched if not git_ok("diff", "--quiet", "HEAD", "--", p)]
    if dirty and not allow_partial:
        out.write("\nWARNING: these paths still differ from HEAD after the last commit; inspect them:\n")
        for p in dirty:
            out.write(f"  {p}\n")
        out.write(f"To undo everything: git reset {start}\n")
        return 2
    if dirty:
        out.write("\nLeft uncommitted on purpose (--allow-partial):\n")
        for p in dirty:
            out.write(f"  {p}\n")
    else:
        out.write("\nHEAD now matches the working tree for every touched path.\n")
    out.write(f"To undo everything: git reset {start}\n")
    return 0


# ------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="list changed files and numbered hunks")
    p_inspect.add_argument("paths", nargs="*", help="limit to these paths (default: whole repo)")
    p_inspect.add_argument("--context", type=int, default=DEFAULT_CONTEXT,
                           help=f"unchanged lines to show around each hunk (default {DEFAULT_CONTEXT})")
    p_inspect.set_defaults(func=cmd_inspect)

    p_apply = sub.add_parser("apply", help="create the commits described by a plan file")
    p_apply.add_argument("plan", help="path to the JSON plan")
    p_apply.add_argument("--dry-run", action="store_true", help="show what each commit would contain, change nothing")
    p_apply.add_argument("--allow-partial", action="store_true",
                         help="permit changed lines that no commit claims; they stay in the working tree")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SplitError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
