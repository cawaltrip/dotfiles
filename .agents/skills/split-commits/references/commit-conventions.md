# Commit conventions in this repo

Everything here was derived from `git log`. Conventions drift, so before
writing messages run `git log --oneline -40` and prefer what the recent
history actually does over anything written below.

## Shape

```
<type>(<scope>): <subject>
```

- Subject in the imperative, lowercase first letter, no trailing period,
  ideally under 60 characters: `add glow`, `update config`, `remove omnifocus from core install`.
- Subject only. History has no bodies, no footers, and no `Co-Authored-By`
  trailers, so do not add any.
- Almost every non-merge commit carries a scope. Leave it off only for
  repo-wide changes with no natural home.

## Types

| Type | Use it for | Real examples |
|---|---|---|
| `chore` | adding, removing, or updating packages; config tweaks; maintenance | `chore(packages): add glow`, `chore(iterm2): update config`, `chore(zsh): update EDITOR` |
| `feat` | a new tool together with its config, or a new capability in the install pipeline | `feat(ghostty): add new terminal emulator`, `feat(packages): trust taps when adding`, `feat(git): add global gitignore` |
| `fix` | something was broken and now works | `fix(zsh/rg): fix env var declaration`, `fix(packages): install groups correctly` |
| `refactor` | restructure with no behavior change | `refactor(packages): split k8s packages to their own group` |
| `docs` | documentation only | `docs: updated initialization steps` |

`chore` is by far the most common type for `packages.yaml`. Reach for `feat`
only when the commit gives the machine something new to do (a new tool with
its own config, a new pipeline behavior), not merely because a package is new.

## Scopes

| Files | Scope |
|---|---|
| `.chezmoidata/packages.yaml` | `packages`, always. `homebrew` is the retired name for the same file; do not revive it. |
| `.chezmoiscripts/*install-packages*`, `.chezmoitemplates/get_packages.tmpl` | `packages` (the package pipeline) |
| `private_dot_config/<tool>/...`, `Library/Application Support/<tool>/...` | the tool: `zsh`, `iterm2`, `git`, `worktrunk`, `karabiner`, `zed`, `ghostty`, `starship`, `ripgrep`, `awsrun` |
| `private_dot_ssh/...` | `ssh` |
| `.chezmoi.yaml.tmpl`, `.chezmoiignore.tmpl`, general chezmoi plumbing | `chezmoi` |
| a sub-area of a tool | compound: `zsh/rg`, `xbar/ccusage` |

Paths are chezmoi *source* paths. Strip the `private_`, `dot_`, and `.tmpl`
decorations mentally: `private_dot_config/zsh/conf.d/zsh_aliases.tmpl` is the
zsh config, so the scope is `zsh`.

## packages.yaml changes, mapped to messages

| Change in the diff | Commit |
|---|---|
| one new package entry | `chore(packages): add direnv` |
| several closely related new packages (same ecosystem, installed for the same reason) | `chore(packages): add openjdk and temurin` |
| a new package entry plus its group/profile membership | one commit: `chore(packages): add gitnr` |
| a new package plus its config files elsewhere | one commit across files: `feat(gitnr): add gitnr config` or `feat(ghostty): add new terminal emulator` |
| a package removed, or dropped from a group | `chore(packages): remove omnifocus from core install`, `chore(packages): remove ghidra and imhex from standard security set` |
| entries moved between groups, groups split or merged | `refactor(packages): split k8s packages to their own group` |
| an installer id or name corrected | `chore(packages): update ffmpeg winget id`, `chore(packages): update claude-code package definition`. (History has one `chore(burp-suite): ...` for this; it's the exception, and the scope stays `packages`.) |
| entries moved into alphabetical order, whitespace, comments | `chore(packages): sort tennis and tenv alphabetically` |
| a new key in the schema, or new behavior in the install pipeline | `feat(packages): add preferred manager order for windows` |
| taps or buckets added | `chore(packages): add taps for recent packages` |

## Which changes belong together

A commit should be the smallest change that still makes sense on its own.
The reader of `git log` is looking for "when did X arrive, and what came
with it", so:

- A package definition and the group line that turns it on are one change,
  even though they are far apart in the file. Splitting them leaves a commit
  where the package is defined but never installed.
- A package and the config that only exists because of that package are one
  change. `feat(ghostty): add new terminal emulator` touched both
  `packages.yaml` and the ghostty config.
- Two packages added for the same reason may share a commit
  (`add less and ripgrep`, `add zed and jd`). Two packages that merely happen
  to sit in the same hunk should not (`add temurin` is not the same story as
  `sort tennis and tenv alphabetically`, even though they are adjacent lines).
- A move (deleted here, identical text added there) is one change on its own.
  Do not fold it into whichever package happens to be nearby.
- Removals and unrelated additions never share a commit. `add delta, remove
  webstorm from group` exists in history, but it is the kind of commit this
  skill is here to avoid.
