# packages.yaml schema and resolution rules

The file is `.chezmoidata/packages.yaml` at the chezmoi source root. It is hand-maintained YAML with comments, so edits must preserve layout. These rules are derived from the templates that consume it (`.chezmoitemplates/get_package_data.tmpl`, `get_group_data.tmpl`, `get_manager_repo_data.tmpl`) and the two install scripts under `.chezmoiscripts/`. When the templates and this document disagree, the templates win; update this document.

## Contents

1. Top-level layout
2. How a package entry resolves (the rule everything else follows from)
3. Installer keys per OS
4. Homebrew: formula vs cask, taps
5. winget, msstore
6. scoop and buckets
7. pipx
8. Groups
9. Profiles
10. Ordering and style conventions
11. Known quirks

## 1. Top-level layout

```yaml
packageManagement:
  defaultManagers:        # osid -> default installer (darwin: brew, windows: winget, ...)
  preferedManagerOrder:   # (sic) per-OS preference when a package exists in several managers
    windows: [winget, scoop, pipx]
  packages:               # one entry per package key; this is the registry
  groups:                 # named lists of package keys
  profiles:               # which groups/packages/taps/buckets a machine gets
```

The config template (`.chezmoi.yaml.tmpl`) always applies the profiles `core`, the current `osid` (`darwin` or `windows`), and `unixlike` on macOS/Linux, plus `personal` and/or `work` depending on the machine.

## 2. How a package entry resolves

For the current OS, the template takes the entry `packages.<key>`:

| Entry shape | What gets installed |
|---|---|
| `key: {}` or `key:` (null) | `<default installer> <key>` on every OS |
| `key: {darwin: some-name}` | on darwin: `brew "some-name"`; on any OS **without** a key: `<default installer> <key>` |
| `key: {darwin: {cask: tok}}` | on darwin: `cask "tok"` |
| `key: {windows: Pub.Name}` | on windows: `winget install Pub.Name` |
| `key: {windows: {scoop: {name: n, source: b}}}` | on windows: scoop app `n` from bucket `b` |
| `key: {windows: {pipx: n}}` | on windows: `pipx install n` |
| `key: {windows: {msstore: id}}` | on windows: winget from the msstore source |

Two consequences drive most decisions:

- **Minimal form.** If the identifier on an OS equals the key and uses the default installer, do not write that OS key at all. `gh: {windows: GitHub.cli}` is complete; on darwin it resolves to `brew "gh"`. Writing `darwin: gh` is redundant. `{}` means "the key is the identifier everywhere".
- **Absence is not exclusion.** A missing OS key means "install `<key>` with the default installer", not "skip". A macOS-only tool with `key: {darwin: {cask: x}}` will, on Windows, become `winget install key` and fail or install the wrong thing. Exclusion happens in the **group**, by listing the key under the group's `darwin:` (or `windows:`) sub-list instead of `shared:`.

Exactly one installer key per OS. The template reads `first (keys entry)` and silently misbehaves if there are two.

## 3. Installer keys per OS

| OS | string value means | explicit keys |
|---|---|---|
| `darwin` | brew formula | `brew`, `cask` |
| `windows` | winget package identifier | `winget` (rare, same as string), `scoop`, `pipx`, `msstore` |

Formulae and casks are written in the string form or under `brew:` interchangeably; the file mostly uses the string form for formulae and `cask:` for casks. Prefer that.

## 4. Homebrew

- Casks are GUI apps, fonts (`font-*`), and a few CLIs distributed as binaries (e.g. `gcloud-cli`, `claude-code@latest`). Formulae are everything else. When a name exists as both (e.g. `docker`), the GUI app is the cask (`docker-desktop`) and the CLI is the formula; pick based on what the user wants and say which you chose.
- Versioned formulae use `@`: `python@3.12`, `google-chrome@dev`, `visual-studio-code@insiders`.
- **Third-party taps** appear in the identifier as `user/repo/name` (`hashicorp/tap/terraform`, `koekeishiya/formulae/yabai`, `terraform-linters/tap/tflint` for a cask). The tap `user/repo` must be listed under `profiles.unixlike.taps` (machine-wide) or `profiles.personal.taps` (personal machines only). `brew` treats `user/homebrew-repo` and `user/repo` as the same tap; the file has both spellings. Default new taps to `unixlike`.
- Homebrew core formulae are looked up at `https://formulae.brew.sh/api/formula/<name>.json`, casks at `/api/cask/<token>.json`. Third-party taps are GitHub repos named `user/homebrew-repo` with `Formula/<name>.rb` or `Casks/<name>.rb`.

## 5. winget and msstore

- Identifiers are fully qualified `Publisher.Name[.Variant]`: `JetBrains.GoLand`, `Microsoft.PowerShell`, `Python.Python.3.12`, `BurntSushi.ripgrep.MSVC`. A moniker like `goland` or `ripgrep` is **never** valid here even though `winget install goland` works interactively; the script imports by identifier. Every valid identifier contains at least one `.`.
- Resolve monikers with `scripts/lookup.py`, which queries the same pre-indexed source database `winget search` uses. Verify any identifier you recall from memory the same way.
- Microsoft Store apps use `msstore: <12-char id>` (e.g. `9PMC9MN3ZZ85`).
- The install uses `--ignore-unavailable`, so a wrong identifier fails silently on the machine. Correctness has to happen here.

## 6. scoop and buckets

- Entry shape is always `scoop: {name: <app>, source: <bucket>}`. Both fields are required; the install script reads both.
- `source` is a bucket **name** that must exist under `profiles.windows.buckets` with a `source:` URL. Official buckets live at `https://github.com/ScoopInstaller/<Bucket>` (Main, Extras, Versions, Java, Games, Nonportable, PHP, Sysinternals, Nerd-Fonts). Keep an existing bucket's URL as-is even if it points at a fork.
- Use scoop when winget has no package or when the user asks for scoop. `preferedManagerOrder.windows` is `winget, scoop, pipx`; managers are evaluated in that order and the first confirmed match ends the search. A package confirmed on winget is not also looked up on scoop or PyPI, and those managers are not offered as alternatives: the entry holds exactly one Windows installer.

## 7. pipx

`windows: {pipx: <pypi-name>}` for Python CLIs that have no winget or scoop package (`checkov`, `poetry`, `vermin`). On darwin the same tools are usually formulae, so the darwin side is normally just `{}`-style default.

## 8. Groups

Two shapes exist:

```yaml
  groups:
    aws:                 # flat list: applies on every OS
      - aws-cdk
      - awscli
    dev:                 # per-OS mapping
      shared:            # every OS
        - gh
      darwin:            # only darwin
        - jaq
      windows:
        - jq
      # unixlike:        # darwin + linux, also valid
```

- A group name must exist under `groups` to be referenced from a profile; a package key must exist under `packages` to be listed in a group.
- Place a package in `shared` only if its entry resolves correctly on every OS the group is applied on. Otherwise place it under the specific OS. When adding an OS-specific package to a flat-list group, convert the group to the mapping shape (existing items become `shared`).
- Empty placeholders exist (`dev-dotnet:` null, `dev-swift: {}`); replace the placeholder with a real mapping when adding the first member.
- A new group is inert until a profile lists it under `groups:`. Ask which profiles (`personal`, `work`, both) should get it.

## 9. Profiles

```yaml
  profiles:
    unixlike:
      taps: [...]        # brew taps for every mac/linux machine
      groups: [aws]
      packages: []
    windows:
      buckets:
        main:
          source: https://github.com/ScoopInstaller/Main.git
    personal:
      taps: [...]        # personal-only taps
      groups: [...]
      packages: [...]    # ad-hoc packages outside groups
    work:
      taps:              # null is fine when empty
      groups: [...]
```

Groups and packages lists in profiles are alphabetical. Taps and buckets are in insertion order; append.

## 10. Ordering and style conventions

- `packages` keys are alphabetical (case-insensitive, digits before letters). Group members are alphabetical within each list, with occasional drift; insert at the alphabetical position rather than appending.
- Two-space indentation, sequences indented under their key, unquoted scalars unless YAML would misread them (`3.10` would become a float, so quote it).
- Key names are lowercase, hyphenated, and descriptive of the tool rather than of one manager's identifier (`nodejs`, not `OpenJS.NodeJS`; `chrome`, not `google-chrome`). For versioned tools use `python3.12`, `corretto21`.
- Inline `# TODO` comments are used to flag follow-ups (e.g. no native Windows package yet). Adding one when you skip an OS is welcome.
- Commit messages in this repo look like `chore(packages): add glow`, `chore(homebrew): add taps for recent packages`, `feat(shell): add atuin shell history`.

## 11. Known quirks

- The key is spelled `preferedManagerOrder` (one r). Read it as-is.
- The winget import runs with `--ignore-unavailable` and scoop import does not verify buckets, so mistakes surface only as silently missing tools on the next machine. That is why the skill verifies identifiers against the real indexes before writing.
- Several existing group members have no `packages` entry (`chezmoi`, `pipx`); `scripts/check.py` reports these as pre-existing warnings. Do not "fix" them as part of an unrelated addition unless asked.
- The templates' error list for a malformed entry appends an empty string, so a two-installer-key entry produces no useful error at apply time. `check.py` catches it beforehand.
