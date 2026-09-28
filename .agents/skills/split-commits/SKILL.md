---
name: split-commits
description: >-
  Commit the working tree of this chezmoi dotfiles repo as a series of small
  conventional commits, one per logical change, in the repo's own
  `type(scope): subject` style. Use this whenever the user asks to commit,
  check in, or "clean up and commit" changes here, and especially when
  .chezmoidata/packages.yaml has several packages added, removed, or moved at
  once. Trigger even if the user never says "split", mentions only one file,
  or just says "commit this" or "commit my packages"; a single tangled file is
  exactly the case this skill exists for. Do not use it to amend, rebase, or
  rewrite commits that already exist.
---

# split-commits

One `chore(packages): add various packages` commit hides which package arrived
when, and why. The user edits `packages.yaml` in batches and wants the history
to read as if each change had been committed on its own. The messages are the
easy part. The hard part is staging pieces of a single file in sequence
without touching the working tree, and `scripts/split_commits.py` does that
deterministically. Your job is to decide what the logical changes are, name
them the way this repo names things, and hand the script a plan.

Paths beginning with `scripts/` or `references/` are relative to this skill's
directory. Run the script with `python3`; it only needs the standard library.

## 1. Look before grouping

```bash
git status --short
git log --oneline -20                       # calibrate: this is the style to match
python3 scripts/split_commits.py inspect    # numbered zero-context hunks
```

`inspect` prints every changed tracked file as hunks `H1`, `H2`, ... with
line numbers: `+` lines index the working-tree file, `-` lines index HEAD's
copy. Anything it can only stage as a whole file (new, deleted, renamed,
binary) is listed separately. Two lines of surrounding context are shown; if
you still can't tell which YAML section a hunk lives in (a group membership
line looks identical to a profile line), open the file around those numbers
with `sed -n`. Pass paths to `inspect` when the user asked about specific
files.

Commit on the branch the user is already on, even if that is `main`. The
changes being committed already live in this working tree; the worktree
convention exists for starting new work, and moving uncommitted edits into a
worktree (stash, checkout, re-apply) is exactly the kind of shuffle that loses
them. Don't create a worktree, switch branches, or stash for this task.

If `git status` shows something already staged, unstage it with `git reset -q`
and fold those changes into the plan. Nothing is lost (the working tree keeps
the edits) and the script refuses to run against a dirty index anyway, because
a stray staged file would silently ride along in the first commit.

## 2. Decide what the logical changes are

A commit is the smallest change that still makes sense alone. Read the hunks
and ask "what story does this tell?" rather than "what is contiguous?". The
rules that matter in this repo:

- **A package and the line that installs it are one change.** `gitnr: {}`
  under `packages:` and `- gitnr` under a group are two hunks hundreds of lines
  apart, but a commit with only the definition adds a package nobody installs.
- **A package and its config are one change, across files.** If a new entry in
  `packages.yaml` arrives with `private_dot_config/<tool>/...`, that's a
  `feat(<tool>)` commit spanning both, like `feat(ghostty): add new terminal
  emulator` did.
- **Closely related packages may share a commit.** Same ecosystem or same
  reason for installing: `add openjdk and temurin`, `add less and ripgrep`.
  Adjacency in the file is not relatedness: `temurin: {}` sitting right above
  a relocated `tennis:` block is two different stories.
- **A move is its own change.** Identical text deleted in one hunk and added
  in another (usually re-alphabetizing) gets one commit and nothing else.
  Select the added lines by number when they share a hunk with something
  unrelated, as in `"new": ["445-451"]` alongside `"hunks": ["H7"]`.
- **Schema or pipeline changes stand apart from package adds.** A new key like
  `preferedManagerOrder` or an edit to the install script is a `feat` or
  `chore` on the pipeline, never bundled with the packages added the same day.
- **Removals never share a commit with unrelated additions.**
- **Commit what is there.** If you notice a typo (`prefered`), a package that
  is defined but not in any group, or a suspicious id, mention it in the
  report; don't edit the user's changes on the way to committing them.

Order the commits so each one would make sense if the user stopped there:
pipeline changes first, then additions, then moves and cleanups.

## 3. Write the messages

Read `references/commit-conventions.md`. The short version: `type(scope):
subject`, imperative, lowercase, no period, no body, no trailers. The scope
for `packages.yaml` is always `packages`. `chore` for adding, removing, and
updating packages; `feat` for a new tool with its config or a new pipeline
capability; `refactor` for regrouping; `fix` when something was broken. When
history and the reference disagree, follow recent history.

## 4. Plan, dry-run, apply

Write the plan as JSON to a temp file outside the repo, never into the
working tree, so it can't be swept into a commit. `PLAN=$(mktemp -d)/plan.json`
works on both macOS and Linux (BSD `mktemp` rejects a suffix after the `X`s). Each entry is a message plus the changes it owns:

```json
{"commits": [
  {"message": "chore(packages): add gitnr",
   "changes": [{"path": ".chezmoidata/packages.yaml", "hunks": ["H4", "H9"]}]},
  {"message": "chore(packages): sort tennis and tenv alphabetically",
   "changes": [{"path": ".chezmoidata/packages.yaml", "new": ["445-451"], "hunks": ["H7"]}]},
  {"message": "feat(lazygit): add lazygit config",
   "changes": [{"path": ".chezmoidata/packages.yaml", "hunks": ["H2", "H6"]},
               {"path": "private_dot_config/lazygit/config.yml", "whole": true}]}
]}
```

`hunks` takes ids from `inspect`; `new` and `old` take line numbers or ranges
(`"12"`, `"12-15"`) for splitting inside a hunk; `whole` stages a path as-is
and is the only option for untracked or deleted files.

```bash
python3 scripts/split_commits.py apply --dry-run "$PLAN"   # read it: does each commit tell one story?
python3 scripts/split_commits.py apply "$PLAN"
```

The script rejects a plan that leaves any changed line unassigned, assigns a
line twice, or names a line that isn't a change, and says exactly which. Fix
the plan rather than reaching for `--allow-partial`; that flag is only for
when the user explicitly wants some edits left uncommitted. After the last
commit it verifies HEAD matches the working tree for every touched path and
prints an undo command (`git reset <sha>`), which restores the pre-run state
without touching files.

Do not fall back to `git add -p`, hand-editing the file between commits, or
stashing when the script complains; the complaint is about the plan, and the
fallbacks are how partial staging goes wrong (a shared stash stack, an edit
that drifts from the original). If the script itself errors, stop and show
the user the message.

## 5. Report

Relay the script's summary table (sha, message, line counts) and add only what
it can't know: anything you chose to group and why, anything you noticed but
deliberately left alone, and the undo command. Do not push, do not run
`chezmoi apply`, and do not add `Co-Authored-By` or other trailers; history
has none.

## Files in this skill

- `scripts/split_commits.py`: `inspect` and `apply`. Run this.
- `scripts/test_split_commits.py`: unit tests (`python3 scripts/test_split_commits.py`).
- `references/commit-conventions.md`: types, scopes, and message patterns derived from this repo's history, with a table mapping `packages.yaml` changes to messages.
- `evals/`: test prompts and `fixtures/make-fixture.sh`, which builds scratch clones with known tangled diffs.
