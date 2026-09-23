#!/usr/bin/env python3
"""Grade one split-commits eval run deterministically.

    grade.py <eval-name> <run-dir>

<run-dir> holds `repo/` (the scratch clone after the agent finished) and
`outputs/`. Writes <run-dir>/grading.json in the skill-creator format
(expectations[] with text/passed/evidence, plus summary). Everything is
checked against the git history of `repo/` itself, not against what the agent
claimed in its report. A fresh reference clone is built to confirm the final
file contents are exactly what the user had in the working tree.

    grade.py --list <eval-name>    print the assertion texts (for eval_metadata.json)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
BASE = (FIXTURES / "BASE_COMMIT").read_text().strip()
PKG = ".chezmoidata/packages.yaml"
SUBJECT = re.compile(r"^(chore|feat|fix|refactor|docs|style|perf|test|ci)\(([a-z0-9][a-z0-9/._-]*)\): [a-z]")
PKG_KEY = re.compile(r"^    ([A-Za-z0-9@._-]+):")   # 4-space key = entry under packages:


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@dataclass
class Commit:
    sha: str
    subject: str
    body: str
    files: list[str]
    added: dict[str, list[str]]
    removed: dict[str, list[str]]

    @property
    def type_scope(self) -> tuple[str, str] | None:
        m = SUBJECT.match(self.subject)
        return (m.group(1), m.group(2)) if m else None

    def pkg_added(self) -> list[str]:
        return self.added.get(PKG, [])

    def pkg_removed(self) -> list[str]:
        return self.removed.get(PKG, [])

    def new_package_keys(self) -> set[str]:
        """Package entries whose definition this commit introduces (moves excluded)."""
        added = {m.group(1) for l in self.pkg_added() if (m := PKG_KEY.match(l))}
        removed = {m.group(1) for l in self.pkg_removed() if (m := PKG_KEY.match(l))}
        return added - removed

    def __str__(self) -> str:
        return f"{self.sha[:7]} {self.subject}"


def load_commits(repo: Path) -> list[Commit]:
    raw = git(repo, "log", "--reverse", "--format=%H%x00%s%x00%b%x01", f"{BASE}..HEAD")
    commits = []
    for rec in raw.split("\x01"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, subject, body = rec.split("\x00")
        files = git(repo, "show", "--format=", "--name-only", sha).split()
        added: dict[str, list[str]] = {}
        removed: dict[str, list[str]] = {}
        current = None
        for line in git(repo, "show", "--format=", "-U0", "--no-color", sha).splitlines():
            if line.startswith("+++ "):
                current = line[6:] if line.startswith("+++ b/") else None
            elif line.startswith("--- ") or line.startswith("@@") or line.startswith("diff ") or line.startswith("index "):
                continue
            elif current and line.startswith("+"):
                added.setdefault(current, []).append(line[1:])
            elif current and line.startswith("-"):
                removed.setdefault(current, []).append(line[1:])
        commits.append(Commit(sha, subject, body.strip(), files, added, removed))
    return commits


def reference_files(fixture: str) -> dict[str, bytes]:
    """Exact working-tree content the user had, per changed path."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "ref"
        subprocess.run([str(FIXTURES / "make-fixture.sh"), fixture, str(dest)], check=True, capture_output=True)
        paths = git(dest, "status", "--porcelain", "--untracked-files=all").splitlines()
        out = {}
        for p in paths:
            path = p[3:]
            out[path] = (dest / path).read_bytes()
        return out


# ------------------------------------------------------------------ assertions

Result = tuple[str, bool, str]


def common_checks(repo: Path, commits: list[Commit], fixture: str, lo: int, hi: int) -> list[Result]:
    res: list[Result] = []
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    res.append(("Commits landed on the branch the user was on (main), not a new branch or worktree",
                branch == "main" and bool(commits), f"HEAD is on '{branch}', {len(commits)} commit(s) since base"))
    status = git(repo, "status", "--porcelain", "--untracked-files=all").strip()
    res.append(("Working tree is clean afterwards (everything committed, nothing left over)",
                status == "", f"git status --porcelain: {status or '(empty)'}"))
    ref = reference_files(fixture)
    mismatched = []
    for path, want in ref.items():
        try:
            have = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{path}"], capture_output=True, check=True).stdout
        except subprocess.CalledProcessError:
            have = b"<missing>"
        if have != want:
            mismatched.append(path)
    res.append(("Final committed content is byte-identical to the user's edits (nothing altered, dropped, or 'fixed')",
                not mismatched, "all paths match" if not mismatched else f"differs: {mismatched}"))
    res.append((f"Between {lo} and {hi} commits were created",
                lo <= len(commits) <= hi, "; ".join(str(c) for c in commits) or "no commits"))
    bad = [c.subject for c in commits if not SUBJECT.match(c.subject) or c.subject.endswith(".") or len(c.subject) > 72]
    res.append(("Every subject is `type(scope): lowercase imperative`, no trailing period, <=72 chars",
                not bad and bool(commits), "all conform" if not bad else f"nonconforming: {bad}"))
    bodies = [str(c) for c in commits if c.body]
    res.append(("No commit has a body or trailer (history has none; no Co-Authored-By)",
                not bodies and bool(commits), "all subject-only" if not bodies else f"has body: {bodies}"))
    wrong_scope = [c.subject for c in commits if c.files == [PKG] and (c.type_scope or ("", ""))[1] != "packages"]
    res.append(("Commits touching only packages.yaml use scope `packages` (never `homebrew`)",
                not wrong_scope and bool(commits), "all `packages`" if not wrong_scope else f"other scopes: {wrong_scope}"))
    return res


def find(commits: list[Commit], needle: str, where: str = "added") -> list[Commit]:
    return [c for c in commits if any(needle in l for lines in getattr(c, where).values() for l in lines)]


def check_packages_mixed(commits: list[Commit]) -> list[Result]:
    res: list[Result] = []
    gitnr = find(commits, "gitnr")
    res.append(("gitnr's package definition and its dev-group line are in the same commit",
                len(gitnr) == 1 and any("gitnr: {}" in l for l in gitnr[0].pkg_added()) and any(l.strip() == "- gitnr" for l in gitnr[0].pkg_added()),
                f"gitnr appears in {[str(c) for c in gitnr]}"))
    move = [c for c in commits if any("tennis:" in l for l in c.pkg_removed())]
    ok = len(move) == 1 and len(move[0].pkg_added()) == 7 and len(move[0].pkg_removed()) == 7
    res.append(("The tennis/tenv re-sort is one commit containing only the 7 moved lines (+7/-7)",
                ok, f"{[str(c) for c in move]}: " + (f"+{len(move[0].pkg_added())}/-{len(move[0].pkg_removed())}" if move else "no commit removes tennis")))
    schema = find(commits, "preferedManagerOrder")
    res.append(("The preferedManagerOrder schema change is its own commit (5 lines, no packages)",
                len(schema) == 1 and len(schema[0].pkg_added()) == 5 and not schema[0].pkg_removed(),
                f"{[str(c) for c in schema]}: +{len(schema[0].pkg_added()) if schema else 0}"))
    allowed = {frozenset({"openjdk", "temurin"})}
    mixed = [(str(c), sorted(k)) for c in commits if len(k := c.new_package_keys()) > 1 and frozenset(k) not in allowed]
    res.append(("No commit bundles unrelated packages (only openjdk+temurin may share one)",
                not mixed, "none bundled" if not mixed else f"bundled: {mixed}"))
    unnamed = [str(c) for c in commits if len(k := c.new_package_keys()) >= 1 and not all(key.lower() in c.subject.lower() for key in k)]
    res.append(("Each package-adding commit names the package(s) in its subject",
                not unnamed, "all named" if not unnamed else f"subject omits package: {unnamed}"))
    return res


def check_package_with_config(commits: list[Commit]) -> list[Result]:
    res: list[Result] = []
    cfg = [c for c in commits if any(f.startswith("private_dot_config/lazygit/") for f in c.files)]
    spans = len(cfg) == 1 and any("lazygit: {}" in l for l in cfg[0].pkg_added()) and any(l.strip() == "- lazygit" for l in cfg[0].pkg_added())
    res.append(("The lazygit commit spans both files: config.yml plus the packages.yaml definition and dev-group line",
                spans, f"config committed in {[str(c) for c in cfg]}; files={cfg[0].files if cfg else []}"))
    res.append(("The lazygit commit is typed feat with scope lazygit (a new tool with its config)",
                bool(cfg) and cfg[0].type_scope == ("feat", "lazygit"), cfg[0].subject if cfg else "no lazygit config commit"))
    htop = find(commits, "htop")
    res.append(("htop is its own single-line commit whose subject names it",
                len(htop) == 1 and htop[0].pkg_added() == ["    htop: {}"] and not htop[0].pkg_removed() and "htop" in htop[0].subject,
                f"{[str(c) for c in htop]}: +{len(htop[0].pkg_added()) if htop else 0}/-{len(htop[0].pkg_removed()) if htop else 0}"))
    pastel = [c for c in commits if any("pastel" in l for l in c.pkg_removed())]
    res.append(("The pastel removal is its own commit with no additions, and the subject says remove + pastel",
                len(pastel) == 1 and not pastel[0].pkg_added() and "remove" in pastel[0].subject and "pastel" in pastel[0].subject,
                f"{[str(c) for c in pastel]}: +{len(pastel[0].pkg_added()) if pastel else 0}"))
    mixed = [str(c) for c in commits if c.pkg_added() and c.pkg_removed()]
    res.append(("No commit mixes a removal with an addition", not mixed, "none" if not mixed else f"mixed: {mixed}"))
    return res


def check_adjacent_and_modify(commits: list[Commit]) -> list[Result]:
    res: list[Result] = []
    zellij = find(commits, "zellij")
    ok = len(zellij) == 1 and any("zellij: {}" in l for l in zellij[0].pkg_added()) and any(l.strip() == "- zellij" for l in zellij[0].pkg_added()) and not any("zig" in l for l in zellij[0].pkg_added())
    res.append(("zellij's definition and shell-group line share one commit that does not include zig",
                ok, f"zellij in {[str(c) for c in zellij]}; lines={zellij[0].pkg_added() if zellij else []}"))
    zig = find(commits, "zig: {}")
    res.append(("zig is its own single-line commit (split out of the hunk it shares with zellij)",
                len(zig) == 1 and zig[0].pkg_added() == ["    zig: {}"] and not zig[0].pkg_removed() and "zig" in zig[0].subject,
                f"{[str(c) for c in zig]}: {zig[0].pkg_added() if zig else []}"))
    ff = find(commits, "Gyan.FFmpeg.Essentials")
    ok = len(ff) == 1 and ff[0].pkg_added() == ["      windows: Gyan.FFmpeg.Essentials"] and ff[0].pkg_removed() == ["      windows: Gyan.FFmpeg"] and "ffmpeg" in ff[0].subject.lower()
    res.append(("The ffmpeg winget-id change is a lone one-line modification whose subject names ffmpeg",
                ok, f"{[str(c) for c in ff]}: +{ff[0].pkg_added() if ff else []} -{ff[0].pkg_removed() if ff else []}"))
    res.append(("The ffmpeg change is typed chore or fix (an id correction, not a feature)",
                bool(ff) and (ff[0].type_scope or ("",))[0] in ("chore", "fix"), ff[0].subject if ff else "none"))
    return res


EVALS = {
    "packages-mixed": ("packages-mixed", 6, 8, check_packages_mixed),
    "package-with-config": ("package-with-config", 3, 3, check_package_with_config),
    "adjacent-and-modify": ("adjacent-and-modify", 3, 3, check_adjacent_and_modify),
}


def assertion_texts(name: str) -> list[str]:
    """Assertion texts without running anything (for eval_metadata.json)."""
    fixture, lo, hi, _ = EVALS[name]
    dummy_repo = None  # common_checks needs a repo; reproduce texts statically instead
    common = [
        "Commits landed on the branch the user was on (main), not a new branch or worktree",
        "Working tree is clean afterwards (everything committed, nothing left over)",
        "Final committed content is byte-identical to the user's edits (nothing altered, dropped, or 'fixed')",
        f"Between {lo} and {hi} commits were created",
        "Every subject is `type(scope): lowercase imperative`, no trailing period, <=72 chars",
        "No commit has a body or trailer (history has none; no Co-Authored-By)",
        "Commits touching only packages.yaml use scope `packages` (never `homebrew`)",
    ]
    specific = [t for t, _, _ in EVALS[name][3]([])]
    return common + specific


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--list":
        print(json.dumps(assertion_texts(argv[1]), indent=2))
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    name, run_dir = argv[0], Path(argv[1])
    fixture, lo, hi, specific = EVALS[name]
    repo = run_dir / "repo"
    commits = load_commits(repo)
    results = common_checks(repo, commits, fixture, lo, hi) + specific(commits)
    expectations = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in results]
    passed = sum(1 for e in expectations if e["passed"])
    grading = {
        "expectations": expectations,
        "summary": {"passed": passed, "failed": len(expectations) - passed, "total": len(expectations),
                    "pass_rate": round(passed / len(expectations), 3) if expectations else 0.0},
    }
    # timing.json beside grading.json is picked up by aggregate_benchmark.py (time + tokens).
    (run_dir / "grading.json").write_text(json.dumps(grading, indent=2) + "\n")
    for e in expectations:
        print(("PASS " if e["passed"] else "FAIL ") + e["text"] + "\n      " + e["evidence"])
    print(f"\n{passed}/{len(expectations)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
