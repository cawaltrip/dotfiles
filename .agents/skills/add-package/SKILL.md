---
name: add-package
description: Add a package to the chezmoi dotfiles registry at .chezmoidata/packages.yaml with correct identifiers for every manager - Homebrew formula vs cask (adding third-party taps to the profile), fully qualified winget Publisher.Name identifiers (never monikers), scoop name plus bucket (adding the bucket when missing), and pipx - then place it in an existing or new group and profile. Use this whenever the user wants to add, install, track, or manage a tool, app, CLI, or font through their dotfiles or chezmoi setup, mentions packages.yaml, brew, cask, winget, scoop, pipx, tap, or bucket, or says things like "add X", "put X in the dev group", "I want X on my Macs and Windows boxes", "track X in chezmoi", even when they only name the tool and never say "package". Also use it to move a package into a group or to add a missing tap or bucket. Not for editing the chezmoi templates or install scripts themselves.
---

# add-package

Add one or more packages to `.chezmoidata/packages.yaml` so the next `chezmoi apply` installs them on every machine that should have them. The file is the single registry the install scripts read; it covers macOS (Homebrew) and Windows (winget, scoop, pipx) today.

Three scripts do the deterministic work. Paths beginning with `scripts/` or `references/` are relative to this skill's directory; run them with `python3` (or `python` on Windows) from the repo root.

- `scripts/lookup.py NAME` resolves a name against the real indexes and proposes an entry.
- `scripts/apply.py` edits the file as text (it is full of comments), inserts alphabetically, adds taps and buckets, places the package in a group, prints a diff, and refuses changes that break the structure.
- `scripts/check.py` runs the structural checks on their own.

Why scripts rather than hand edits: the install side runs `winget import --ignore-unavailable` and trusts every tap and bucket name, so a moniker instead of an identifier, a missing bucket, or a second installer key does not error anywhere. It just means the tool silently never shows up on the next machine. The scripts verify identifiers before anything is written.

## Arguments

```
/add-package <name> [<name> ...] [--manager brew|cask|winget|scoop|pipx] [--group <name>|none]
             [--os darwin|windows] [--tap user/repo] [--bucket <bucket>] [--no-prompt] [and commit]
```

Plain English works too: "add lazygit to the dev group", "track yabai from the koekeishiya/formulae tap, mac only", "add vscode insiders, cask on mac and scoop on windows".

- The name is what the user calls the tool. It becomes the registry key (lowercase, hyphenated) unless it is clearly a manager identifier, in which case pick a friendly key (`JetBrains.GoLand` becomes `goland`).
- `--manager` says which manager the typed name belongs to. It does **not** restrict the OS: both macOS and Windows are still filled in. `--manager scoop tenv` means "tenv is the scoop app name; find the Homebrew side yourself".
- `--os` restricts to one OS. Without it, fill in both and tell the user about any OS where nothing was found.
- `and commit` opts into a commit. Otherwise leave the change uncommitted and show the diff; that is how this repo is worked on.

## Workflow

### 1. Orient

The file is `.chezmoidata/packages.yaml` at the repo root unless the user points at another copy; then pass `--file PATH` to `apply.py` and `check.py` (before or after the subcommand). `lookup.py` never reads the registry, so it takes no `--file`. Run `python3 scripts/apply.py context` once: it lists the package keys, every group with its shape and members, the profiles with their groups, and the taps and buckets already declared. This is what you need to choose a group and to notice that a tap or bucket already exists.

For each requested name run `python3 scripts/apply.py show <key>`. If the key is already defined, say so and stop unless the request is about its group, tap, or bucket. Use `apply --replace` only when the user wants the existing stanza rewritten.

### 2. Look up

```
python3 scripts/lookup.py <name> [--manager M] [--os darwin|windows] [--tap user/repo] [--winget-id Publisher.Name] [--bucket versions]
```

Read `suggested_entry`, `suggested_placement`, `taps_needed`, `buckets_needed`, and above all `notes`. `windows.evaluated` and `windows.skipped` say which managers were consulted; skipped ones were never looked up. The notes flag ambiguity: both a formula and a cask, several winget candidates, nothing found on one OS, a deprecated formula. Pass `--tap` when the user names a tap or you know the formula lives outside core; pass `--winget-id` to verify an identifier you recall. The first winget lookup downloads a 20 MB index and caches it for a day, so expect a short pause.

When the lookup finds nothing on macOS and `brew` is installed, the output includes `brew search` results. Use them, or your own knowledge, to try the right token, and look it up again. Never write an identifier the lookup could not confirm.

### 3. Decide the identifiers

`references/schema.md` has the full rules with examples. The ones that decide most cases:

- **Minimal form.** An OS whose identifier equals the key and uses the default manager is omitted. `lazygit: {windows: JesseDuffield.lazygit}` is complete; on macOS it resolves to `brew "lazygit"`. `{}` means the key is the identifier everywhere.
- **Absence is not exclusion.** A missing OS key means "install the key with the default manager", not "skip". A macOS-only tool must be kept out of `shared` group lists and put under the group's `darwin:` list. `suggested_placement` already reflects this.
- **Formula vs cask.** Casks are GUI apps, fonts, and a few binary-only CLIs; write them as `darwin: {cask: token}`. Formulae are the string form. When both exist, the CLI is the formula and the app is the cask; choose by what the user wants and say which you picked.
- **Services.** When the user wants a formula running in the background ("add redis and keep it running"), write `darwin: {brew: {name: redis, service: true}}`. `name` is required even when it equals the key. Only do this when asked, and only for a formula that defines a service; `references/schema.md` §4 has the details.
- **winget identifiers are fully qualified** (`Publisher.Name`, always containing a dot) and verified by the lookup. A moniker such as `goland` works at an interactive prompt but not in the import file.
- **scoop needs `name` and `source`**, and the bucket must be declared under `profiles.windows.buckets`. Put `buckets_needed` in the spec and `apply.py` adds any missing bucket with its GitHub URL.
- **Taps.** A formula or cask written as `user/repo/name` needs `user/repo` under a profile's `taps`. Put `taps_needed` in the spec; `apply.py` appends to `profiles.unixlike.taps` (or `taps_profile: personal` if the tool is personal-only) and skips taps already present under either spelling.
- **Windows managers are tried in preference order** (winget, then scoop, then pipx, from `preferedManagerOrder`) and the first confirmed match wins. The lookup does not evaluate the managers after it (they appear under `windows.skipped`), and neither should you: the registry holds one Windows installer per package, so a scoop or PyPI alternative to a confirmed winget package is noise in the report and a wasted lookup. `--manager` pins one manager instead, and the user asking for scoop does the same.

### 4. Decide the group

If the user named a group (or said "no group"), use it. Otherwise, in an interactive session, ask with one `AskUserQuestion` call:

- First option, marked recommended: the existing group whose members are most like this tool. Reason from what the tool is and from the group's current members (a Go IDE belongs with `go` in `dev-golang`; a window manager with `moom` in `core.darwin`). One sentence of justification in the description.
- One or two other plausible existing groups.
- "New group" and "No group" as the last options.

If the answer is a new group, ask which profiles should receive it (`personal`, `work`, both, none for now). A group nobody lists is inert, and only the user knows which machines want it. Bundle this with any identifier question (formula vs cask, several winget matches) so the user answers once.

Do not ask about things the lookup already settled, and do not ask when the user passed `--no-prompt` or the session cannot prompt. In that case default to no group, prefer the formula, take the single strong winget match, skip an OS with nothing found, and list every assumption in the report.

### 5. Apply

Write a spec and run it. `apply.py` prints the unified diff and a JSON report, compares structural findings before and after, and refuses to write if the change introduces an error (a missing bucket, a duplicate key). Use `--dry-run` first when the change is unusual; for a routine addition, one run is fine.

```bash
cat > /tmp/add-package.json <<'JSON'
{
  "package": {"key": "yabai", "entry": {"darwin": "koekeishiya/formulae/yabai"}},
  "taps": ["koekeishiya/formulae"],
  "group": {"name": "core", "placement": "darwin"}
}
JSON
python3 scripts/apply.py apply /tmp/add-package.json
```

Spec fields: `package.key`, `package.entry` (`{}` allowed), optional `group` (`name`, `placement` of `shared`/`darwin`/`windows`/`unixlike`, `profiles` only for a new group), optional `taps` (+ `taps_profile`), optional `buckets` (`name: url`). Flat-list groups are converted to the `shared`/OS shape automatically when an OS-specific placement needs it.

### 6. Validate on the real file

When you edited the actual source file (not a copy), render the install script for this OS to see the new line come out the other end:

```bash
# macOS
chezmoi execute-template < .chezmoiscripts/run_onchange_darwin_install-packages.sh.tmpl | grep -n '<identifier>'
# Windows (pwsh)
Get-Content .chezmoiscripts/run_onchange_windows_install-packages.ps1.tmpl | chezmoi execute-template | Select-String '<identifier>'
```

A line only appears if the package is reachable from a profile applied on this machine (`chezmoi data | grep -A5 packagesToInstall` shows which). If it is not, say so rather than reporting a failure. `python3 scripts/check.py` runs the structural checks on the whole file at any time; it reports a few pre-existing warnings (group members with no entry) that are not yours to fix.

### 7. Report

Keep it short and concrete:

- The stanza that was added (as YAML), and the group line(s) added, with the placement and why (shared vs OS-specific).
- Taps or buckets added, if any.
- Any OS left out and what was looked up (so the user can supply a name if they know one).
- Choices made without asking (formula over cask, which winget match). Do not mention managers the lookup skipped; only the one that was used matters to the reader.
- The validation result and the next step: `chezmoi apply` installs it; the change is uncommitted unless they said "and commit", in which case commit as `chore(packages): add <name>` on the current branch.

## Examples

**`/add-package lazygit --group dev`**
Lookup: core formula `lazygit`, winget `JesseDuffield.lazygit` (moniker match). Entry: `lazygit: {windows: JesseDuffield.lazygit}` (darwin omitted, minimal form). Placement: `groups.dev.shared`, alphabetically after `jd`.

**"track yabai from the koekeishiya/formulae tap, mac only, in core"**
Lookup with `--tap koekeishiya/formulae`: formula found in the tap's GitHub repo; nothing on Windows. Entry: `yabai: {darwin: koekeishiya/formulae/yabai}`. Tap appended to `profiles.unixlike.taps`. Placement: `groups.core.darwin` (not `shared`, because on Windows the missing key would mean `winget install yabai`).

**"add vscode insiders, cask on mac, scoop on windows, no group"**
Lookup for `vscode-insiders --manager scoop`: scoop app in the `versions` bucket, which is not declared yet; Homebrew misses on that name, `brew search` shows `visual-studio-code@insiders`, a second lookup with `--manager cask` confirms it. Entry: `darwin: {cask: visual-studio-code@insiders}`, `windows: {scoop: {name: vscode-insiders, source: versions}}`. Bucket `versions` added with `https://github.com/ScoopInstaller/Versions`. No group.

## Several packages at once

Run the lookup for each, collect the questions, and ask once. Apply one spec per package so each diff stays readable and a refusal on one does not block the others. Report per package.
