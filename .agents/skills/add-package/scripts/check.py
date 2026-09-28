#!/usr/bin/env python3
"""Structural checks for the chezmoi package registry (.chezmoidata/packages.yaml).

Usage:
  check.py [--file PATH] [--baseline PATH] [--json]

Findings print one per line as `LEVEL code: message` (or as JSON with --json).
With --baseline, only findings absent from the baseline file are printed, so
pre-existing drift stays quiet and what a change broke stands out.

Exit status: 0 nothing (new) to report, 1 findings, 2 the file could not be parsed
or no YAML parser is available (needs `yq` from mikefarah on PATH, or PyYAML).

Why these checks exist: the install templates read this file with almost no
validation. A second installer key, a scoop app whose bucket is not declared, a
tap that is not listed, or a winget moniker instead of a full identifier all
fail silently on the next machine (`winget import --ignore-unavailable`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass

DEFAULT_FILE = os.path.join(".chezmoidata", "packages.yaml")
DARWIN_INSTALLERS = {"brew", "cask"}
WINDOWS_INSTALLERS = {"winget", "scoop", "pipx", "msstore"}
BREW_KEYS = {"name", "service"}  # keys the darwin install script reads from a `brew:` mapping
GROUP_SUBKEYS = {"shared", "unixlike", "darwin", "windows", "linux"}
CORE_TAPS = {"homebrew/core", "homebrew/cask"}
KEY_RE = re.compile(r"^( *)([^\s#\-][^:]*?):(?:\s|$)")
ITEM_RE = re.compile(r"^( *)- (.*)$")


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning"
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()} {self.code}: {self.message}"


def norm_tap(tap: str) -> str:
    """brew treats `user/homebrew-repo` and `user/repo` as the same tap; compare them that way."""
    user, _, repo = tap.strip().partition("/")
    if repo.startswith("homebrew-"):
        repo = repo[len("homebrew-"):]
    return f"{user}/{repo}".lower()


def tap_of(identifier: str) -> str | None:
    """`user/repo/name` -> `user/repo`; a plain name has no tap."""
    parts = identifier.split("/")
    return "/".join(parts[:2]) if len(parts) >= 3 else None


def load_yaml_text(text: str):
    """Parse YAML into Python data with yq (preferred, present on all of Chris's machines) or PyYAML."""
    if shutil.which("yq"):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            path = tmp.name
        try:
            proc = subprocess.run(["yq", "-o=json", ".", path], capture_output=True, text=True)
        finally:
            os.unlink(path)
        if proc.returncode != 0:
            raise ValueError(proc.stderr.strip() or "yq could not parse the file")
        return json.loads(proc.stdout or "null")
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on the machine
        raise RuntimeError("install `yq` (mikefarah) or PyYAML to parse packages.yaml") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:  # keep one exception type for "the text is not valid YAML"
        raise ValueError(str(exc)) from exc


def duplicate_keys(text: str) -> list[Finding]:
    """YAML parsers keep the last duplicate key silently; catch repeats at any mapping level."""
    findings: list[Finding] = []
    stack: list[tuple[int, dict[str, int]]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        item = ITEM_RE.match(line)
        if item:
            # each `- ` list item is its own mapping scope; keys inside it must not collide with a sibling item's keys
            indent = len(item.group(1))
            while stack and stack[-1][0] > indent:
                stack.pop()
            inner = KEY_RE.match(" " * (indent + 2) + item.group(2))
            if inner:
                stack.append((indent + 2, {inner.group(2).strip(): lineno}))
            continue
        match = KEY_RE.match(line)
        if not match:
            continue
        indent, key = len(match.group(1)), match.group(2).strip()
        while stack and stack[-1][0] > indent:
            stack.pop()
        if not stack or stack[-1][0] < indent:
            stack.append((indent, {}))
        seen = stack[-1][1]
        if key in seen:
            findings.append(Finding("error", "dup-key", f"line {lineno}: `{key}` repeats the key from line {seen[key]} at the same level"))
        else:
            seen[key] = lineno
    return findings


def collect_repos(profiles: dict) -> tuple[set[str], set[str]]:
    taps: set[str] = set()
    buckets: set[str] = set()
    for profile in profiles.values():
        profile = profile or {}
        taps |= {norm_tap(t) for t in (profile.get("taps") or []) if isinstance(t, str)}
        buckets |= set((profile.get("buckets") or {}).keys())
    return taps, buckets


def check_brew_mapping(where: str, ident: dict) -> list[Finding]:
    out: list[Finding] = []
    unknown = sorted(set(ident) - BREW_KEYS)
    if unknown:
        out.append(Finding("error", "brew-shape", f"{where}: a brew mapping only takes {sorted(BREW_KEYS)}, found {unknown}"))
    name = ident.get("name")
    if not isinstance(name, str) or not name.strip():
        out.append(Finding("error", "brew-shape", f"{where}: a brew mapping needs a non-empty `name`"))
    if "service" in ident and not isinstance(ident["service"], bool):
        out.append(Finding("error", "brew-service", f"{where}: `service` must be true or false, got {ident['service']!r}"))
    return out


def check_identifier(where: str, installer: str, ident, taps: set[str], buckets: set[str]) -> list[Finding]:
    out: list[Finding] = []
    if installer == "scoop":
        if not isinstance(ident, dict) or not {"name", "source"} <= set(ident):
            out.append(Finding("error", "scoop-shape", f"{where}: scoop needs a mapping with `name` and `source`"))
        elif ident["source"] not in buckets:
            out.append(Finding("error", "bucket-missing", f"{where}: bucket `{ident['source']}` is not declared under profiles.windows.buckets"))
        return out
    if installer == "brew" and isinstance(ident, dict):
        out += check_brew_mapping(where, ident)
        if not isinstance(ident.get("name"), str) or not ident["name"].strip():
            return out
        ident = ident["name"]  # the tap check below applies to the formula name
    if not isinstance(ident, str) or not ident.strip():
        out.append(Finding("error", "identifier-shape", f"{where}: identifier must be a non-empty string"))
        return out
    if installer in ("brew", "cask"):
        tap = tap_of(ident)
        if tap and norm_tap(tap) not in CORE_TAPS and norm_tap(tap) not in taps:
            out.append(Finding("error", "tap-missing", f"{where}: tap `{tap}` is not declared under any profile's taps"))
    if installer == "winget" and "." not in ident:
        out.append(Finding("warning", "winget-moniker", f"{where}: `{ident}` looks like a moniker; the import needs a fully qualified identifier such as Publisher.Name"))
    return out


def check_packages(packages: dict, taps: set[str], buckets: set[str]) -> list[Finding]:
    out: list[Finding] = []
    for key, entry in packages.items():
        if entry is None or entry == {}:
            continue
        if not isinstance(entry, dict):
            out.append(Finding("error", "entry-shape", f"packages.{key}: expected a mapping or {{}}, got {type(entry).__name__}"))
            continue
        for os_name, value in entry.items():
            where = f"packages.{key}.{os_name}"
            if isinstance(value, str):
                default = "winget" if os_name == "windows" else "brew"
                out += check_identifier(where, default, value, taps, buckets)
            elif isinstance(value, dict):
                if len(value) != 1:
                    out.append(Finding("error", "multi-installer", f"{where}: exactly one installer key is allowed, found {sorted(value) or 'none'}"))
                    continue
                installer, ident = next(iter(value.items()))
                allowed = {"darwin": DARWIN_INSTALLERS, "windows": WINDOWS_INSTALLERS}.get(os_name)
                if allowed is not None and installer not in allowed:
                    out.append(Finding("warning", "unknown-installer", f"{where}: `{installer}` is not one of {sorted(allowed)}"))
                out += check_identifier(where, installer, ident, taps, buckets)
            elif value is None:
                out.append(Finding("warning", "null-os", f"{where}: null means 'install `{key}` with the default installer'; drop the key or write the identifier"))
            else:
                out.append(Finding("error", "entry-shape", f"{where}: expected a string or a one-key mapping"))
    return out


def check_groups(groups: dict, packages: dict) -> list[Finding]:
    out: list[Finding] = []
    for name, group in groups.items():
        if group is None or group == {}:
            continue
        members: list[tuple[str | None, object]] = []
        if isinstance(group, list):
            members = [(None, m) for m in group]
        elif isinstance(group, dict):
            for sub, items in group.items():
                if sub not in GROUP_SUBKEYS:
                    out.append(Finding("warning", "group-subkey", f"groups.{name}.{sub}: not one of {sorted(GROUP_SUBKEYS)}"))
                members += [(sub, m) for m in (items or [])]
        else:
            out.append(Finding("error", "group-shape", f"groups.{name}: expected a list or a mapping of lists"))
            continue
        for sub, member in members:
            where = f"groups.{name}" + (f".{sub}" if sub else "")
            if not isinstance(member, str):
                out.append(Finding("error", "group-member-shape", f"{where}: members must be package keys (strings)"))
            elif member not in packages:
                out.append(Finding("warning", "group-member-undefined", f"{where}: `{member}` has no entry under packages"))
    return out


def check_profiles(profiles: dict, groups: dict, packages: dict) -> list[Finding]:
    out: list[Finding] = []
    for name, profile in profiles.items():
        profile = profile or {}
        for group in profile.get("groups") or []:
            if group not in groups:
                out.append(Finding("error", "profile-group-undefined", f"profiles.{name}.groups: `{group}` is not defined under groups"))
        for pkg in profile.get("packages") or []:
            if pkg not in packages:
                out.append(Finding("warning", "profile-package-undefined", f"profiles.{name}.packages: `{pkg}` has no entry under packages"))
    return out


def run_checks(text: str) -> list[Finding]:
    """All findings for a file's text. Raises RuntimeError when no YAML parser is available."""
    findings = duplicate_keys(text)
    try:
        data = load_yaml_text(text)
    except ValueError as exc:
        return findings + [Finding("error", "yaml-parse", str(exc))]
    root = (data or {}).get("packageManagement") or {}
    packages = root.get("packages") or {}
    groups = root.get("groups") or {}
    profiles = root.get("profiles") or {}
    taps, buckets = collect_repos(profiles)
    return findings + check_packages(packages, taps, buckets) + check_groups(groups, packages) + check_profiles(profiles, groups, packages)


def new_findings(current: list[Finding], baseline: list[Finding]) -> list[Finding]:
    known = set(baseline)
    return [f for f in current if f not in known]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", default=DEFAULT_FILE, help=f"packages file (default {DEFAULT_FILE})")
    parser.add_argument("--baseline", help="only report findings that this file does not already have")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    args = parser.parse_args(argv)

    try:
        with open(args.file, encoding="utf-8") as fh:
            findings = run_checks(fh.read())
        if args.baseline:
            with open(args.baseline, encoding="utf-8") as fh:
                findings = new_findings(findings, run_checks(fh.read()))
    except (OSError, RuntimeError) as exc:
        print(f"check.py: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for finding in findings:
            print(finding)
        if not findings:
            print("check.py: no findings" + (" beyond the baseline" if args.baseline else ""))
    if any(f.code == "yaml-parse" for f in findings):
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
