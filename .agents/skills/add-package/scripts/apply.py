#!/usr/bin/env python3
"""Edit the chezmoi package registry (.chezmoidata/packages.yaml) from a JSON spec.

The file is hand-maintained YAML full of comments, so this script edits it as
text: it finds the right block by indentation, inserts new lines at the
alphabetical position, and leaves every other byte alone. A YAML round-trip
would drop the comments and reflow the layout.

Subcommands
  apply   [--dry-run] [--replace] [--force] SPEC   apply a spec (a path, or `-` for stdin); prints a unified diff
  show    KEY                                      print KEY's stanza and every group/profile listing it
  context                                          JSON: package keys, groups (shape + members), profiles, taps, buckets, manager order

  --file PATH (before or after the subcommand) points at another copy of the registry.

Spec
  {
    "package": {"key": "goland", "entry": {"darwin": {"cask": "goland"}, "windows": "JetBrains.GoLand"}},
    "group":   {"name": "dev-golang", "placement": "shared", "profiles": ["personal"]},
    "taps":    ["hashicorp/tap"],          "taps_profile": "unixlike",
    "buckets": {"versions": "https://github.com/ScoopInstaller/Versions"}
  }
  Only "package" is required. "entry" may be {} (install by key name with the default
  manager). "placement" is shared | unixlike | darwin | windows; a flat-list group is
  converted to the mapping shape when an OS-specific placement needs it. "profiles" is
  used only when the group has to be created. Existing taps/buckets are left alone.

Before writing, the new text is compared with the old one using check.py; the write
is refused (exit 1) if the change introduces structural errors, unless --force.

Exit status: 0 applied or dry-run, 1 refused, 2 bad input or missing block, 3 the package
key already exists (use --replace, or use `show` first).
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check  # noqa: E402

DEFAULT_FILE = check.DEFAULT_FILE
ROOT = "packageManagement"
PLACEMENTS = ("shared", "unixlike", "darwin", "windows")
SUBKEY_ORDER = ("name", "source")  # scoop stanzas always read name then source
KEY_RE = re.compile(r"^([^\s#\-][^:]*?):(?:\s|$)")
HEADER_RE = re.compile(r"^( *)([^\s#][^:]*?):\s*(\{\s*\}|\[\s*\]|~|null)?\s*(#.*)?$")
YAML_SPECIAL_START = set("!&*?|>%@`'\"[]{}#,")
YAML_WORDS = {"", "~", "null", "true", "false", "yes", "no", "on", "off"}
NUMBER_RE = re.compile(r"^[-+]?(\d[\d_]*(\.\d*)?|\.\d+)([eE][-+]?\d+)?$|^0x[0-9a-fA-F]+$|^0o[0-7]+$")


class SpecError(Exception):
    """The spec or the file does not have the expected shape."""


class KeyExists(Exception):
    """The package key is already defined."""


# --------------------------------------------------------------------------- lines

def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def is_noise(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def key_of(line: str) -> str | None:
    match = KEY_RE.match(line.strip())
    return match.group(1) if match else None


def item_of(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("- "):
        return None
    return stripped[2:].split(" #", 1)[0].strip()


def sort_key(name: str) -> list:
    """Case-insensitive natural order: python3.9 sorts before python3.10."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name.lower())]


def scalar(value) -> str:
    """Write a scalar the way the file does (bare) unless YAML would misread it."""
    if isinstance(value, bool):  # `brew: {service: true}` must stay a boolean, not the string "True"
        return "true" if value else "false"
    text = str(value)
    if (text.strip() != text or text.lower() in YAML_WORDS or text[0] in YAML_SPECIAL_START
            or text.startswith("- ") or text.endswith(":") or ": " in text or " #" in text or NUMBER_RE.match(text)):
        return json.dumps(text)
    return text


def replace_line(lines: list[str], index: int, new: str) -> list[str]:
    return lines[:index] + [new] + lines[index + 1:]


def block_end(lines: list[str], start: int) -> int:
    """One past the last line of the block headed by lines[start], including comments indented inside it."""
    base = indent_of(lines[start])
    last = start
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not is_noise(line):
            if indent_of(line) <= base:
                break
            last = i
        elif line.strip() and indent_of(line) > base:
            last = i
    return last + 1


def child_indent(lines: list[str], start: int, end: int) -> int:
    for i in range(start + 1, end):
        if not is_noise(lines[i]):
            return indent_of(lines[i])
    return indent_of(lines[start]) + 2


def children(lines: list[str], start: int, end: int) -> list[tuple[int, str, str]]:
    """Direct children of a block as (index, kind, name); kind is 'key' or 'item'."""
    indent = child_indent(lines, start, end)
    out: list[tuple[int, str, str]] = []
    for i in range(start + 1, end):
        line = lines[i]
        if is_noise(line) or indent_of(line) != indent:
            continue
        item = item_of(line)
        if item is not None:
            out.append((i, "item", item))
            continue
        key = key_of(line)
        if key is not None:
            out.append((i, "key", key))
    return out


def find_child(lines: list[str], start: int, end: int, name: str, kind: str = "key") -> int:
    for i, k, n in children(lines, start, end):
        if k == kind and n == name:
            return i
    return -1


def append_pos(lines: list[str], start: int, end: int) -> int:
    """Right after the last direct child (and its sub-block), ahead of any trailing comments."""
    kids = children(lines, start, end)
    if not kids:
        return start + 1
    last, kind, _ = kids[-1]
    return block_end(lines, last) if kind == "key" else last + 1


def open_header(line: str) -> str:
    """`key: {}` / `key: []` / `key: ~` / `key:` -> `key:` so children can go underneath (trailing comment kept)."""
    match = HEADER_RE.match(line)
    if not match:
        raise SpecError(f"cannot add children under a header that has an inline value: {line.strip()!r}")
    indent, key, _, comment = match.groups()
    return f"{indent}{key}:" + (f" {comment}" if comment else "")


def locate(lines: list[str], path: list[str]) -> tuple[int, int]:
    """(start, end) of the block at `path`, e.g. [ROOT, "groups"]."""
    start, end = -1, len(lines)
    for depth, key in enumerate(path):
        if depth == 0:
            idx = next((i for i, line in enumerate(lines) if indent_of(line) == 0 and key_of(line) == key), -1)
        else:
            idx = find_child(lines, start, end, key)
        if idx < 0:
            raise SpecError(f"`{'.'.join(path[:depth + 1])}` not found in the file")
        start, end = idx, block_end(lines, idx)
    return start, end


def insert_sorted_key(lines: list[str], start: int, end: int, name: str, new_lines: list[str]) -> list[str]:
    for i, kind, child in children(lines, start, end):
        if kind == "key" and sort_key(child) > sort_key(name):
            return lines[:i] + new_lines + lines[i:]
    pos = append_pos(lines, start, end)
    return lines[:pos] + new_lines + lines[pos:]


def insert_sorted_item(lines: list[str], start: int, end: int, item: str) -> tuple[list[str], bool]:
    """Insert `- item` at its alphabetical position; (lines, inserted). No-op if already listed."""
    kids = children(lines, start, end)
    if any(k == "item" and n == item for _, k, n in kids):
        return lines, False
    new = " " * child_indent(lines, start, end) + f"- {item}"
    for i, kind, child in kids:
        if kind == "item" and sort_key(child) > sort_key(item):
            return lines[:i] + [new] + lines[i:], True
    pos = append_pos(lines, start, end)
    return lines[:pos] + [new] + lines[pos:], True


# --------------------------------------------------------------------------- operations

def render_entry(key: str, entry, indent: int) -> list[str]:
    pad = " " * indent
    if not entry:
        return [f"{pad}{key}: {{}}"]
    if not isinstance(entry, dict):
        raise SpecError("package.entry must be a mapping or {}")
    out = [f"{pad}{key}:"]
    for os_name in sorted(entry, key=lambda o: (o != "darwin", o != "windows", o)):
        value = entry[os_name]
        if isinstance(value, str):
            out.append(f"{pad}  {os_name}: {scalar(value)}")
        elif isinstance(value, dict) and len(value) == 1:
            installer, ident = next(iter(value.items()))
            out.append(f"{pad}  {os_name}:")
            if isinstance(ident, dict):
                out.append(f"{pad}    {installer}:")
                ordered = sorted(ident, key=lambda k: (SUBKEY_ORDER.index(k) if k in SUBKEY_ORDER else len(SUBKEY_ORDER), k))
                out += [f"{pad}      {k}: {scalar(ident[k])}" for k in ordered]
            else:
                out.append(f"{pad}    {installer}: {scalar(ident)}")
        else:
            raise SpecError(f"package.entry.{os_name} must be a string or a one-key mapping")
    return out


def upsert_package(lines: list[str], key: str, entry, replace: bool) -> tuple[list[str], str]:
    start, end = locate(lines, [ROOT, "packages"])
    new_lines = render_entry(key, entry, child_indent(lines, start, end))
    idx = find_child(lines, start, end, key)
    if idx >= 0:
        if not replace:
            raise KeyExists(key)
        return lines[:idx] + new_lines + lines[block_end(lines, idx):], "replaced"
    return insert_sorted_key(lines, start, end, key, new_lines), "added"


def add_group_to_profile(lines: list[str], profile: str, group: str) -> list[str]:
    pstart, _ = locate(lines, [ROOT, "profiles", profile])
    lines = replace_line(lines, pstart, open_header(lines[pstart]))
    pend = block_end(lines, pstart)
    gidx = find_child(lines, pstart, pend, "groups")
    if gidx < 0:
        pad = " " * child_indent(lines, pstart, pend)
        gidx = append_pos(lines, pstart, pend)
        lines = lines[:gidx] + [f"{pad}groups:"] + lines[gidx:]
    lines = replace_line(lines, gidx, open_header(lines[gidx]))
    lines, _ = insert_sorted_item(lines, gidx, block_end(lines, gidx), group)
    return lines


def place_in_group(lines: list[str], name: str, placement: str, key: str, profiles) -> tuple[list[str], bool, bool]:
    if placement not in PLACEMENTS:
        raise SpecError(f"group.placement must be one of {PLACEMENTS}")
    gstart, gend = locate(lines, [ROOT, "groups"])
    created = find_child(lines, gstart, gend, name) < 0
    if created:
        pad = " " * child_indent(lines, gstart, gend)
        lines = insert_sorted_key(lines, gstart, gend, name, [f"{pad}{name}:"])
    gstart, _ = locate(lines, [ROOT, "groups", name])
    lines = replace_line(lines, gstart, open_header(lines[gstart]))
    gend = block_end(lines, gstart)
    kids = children(lines, gstart, gend)
    base = indent_of(lines[gstart])
    pad = " " * (base + 2)

    if any(k == "item" for _, k, _ in kids):  # flat list group
        if placement == "shared":
            lines, added = insert_sorted_item(lines, gstart, gend, key)
        else:  # existing items apply everywhere, so they become `shared`
            body = [("  " + line if line.strip() else line) for line in lines[gstart + 1:gend]]
            lines = lines[:gstart + 1] + [f"{pad}shared:"] + body + [f"{pad}{placement}:", f"{pad}  - {key}"] + lines[gend:]
            added = True
    else:
        sub = find_child(lines, gstart, gend, placement)
        if sub < 0:
            rank = PLACEMENTS.index(placement)
            pos = next((i for i, k, n in kids if k == "key" and n in PLACEMENTS and PLACEMENTS.index(n) > rank), None)
            if pos is None:
                pos = append_pos(lines, gstart, gend)
            lines = lines[:pos] + [f"{pad}{placement}:", f"{pad}  - {key}"] + lines[pos:]
            added = True
        else:
            lines = replace_line(lines, sub, open_header(lines[sub]))
            lines, added = insert_sorted_item(lines, sub, block_end(lines, sub), key)

    if created:
        for profile in profiles or []:
            lines = add_group_to_profile(lines, profile, name)
    return lines, created, added


def existing_taps(lines: list[str]) -> set[str]:
    pstart, pend = locate(lines, [ROOT, "profiles"])
    found: set[str] = set()
    for i, kind, _ in children(lines, pstart, pend):
        if kind != "key":
            continue
        tidx = find_child(lines, i, block_end(lines, i), "taps")
        if tidx >= 0:
            found |= {check.norm_tap(n) for _, k, n in children(lines, tidx, block_end(lines, tidx)) if k == "item"}
    return found


def ensure_taps(lines: list[str], taps: list[str], profile: str) -> tuple[list[str], list[str]]:
    have = existing_taps(lines)
    added: list[str] = []
    for tap in taps:
        if check.norm_tap(tap) in have:
            continue
        pstart, _ = locate(lines, [ROOT, "profiles", profile])
        lines = replace_line(lines, pstart, open_header(lines[pstart]))
        pend = block_end(lines, pstart)
        tidx = find_child(lines, pstart, pend, "taps")
        if tidx < 0:
            pad = " " * child_indent(lines, pstart, pend)
            tidx = pstart + 1
            lines = lines[:tidx] + [f"{pad}taps:"] + lines[tidx:]
        lines = replace_line(lines, tidx, open_header(lines[tidx]))
        tend = block_end(lines, tidx)
        pad = " " * child_indent(lines, tidx, tend)
        pos = append_pos(lines, tidx, tend)  # taps are in insertion order; append after the last active one
        lines = lines[:pos] + [f"{pad}- {tap}"] + lines[pos:]
        added.append(tap)
        have.add(check.norm_tap(tap))
    return lines, added


def ensure_buckets(lines: list[str], buckets: dict) -> tuple[list[str], list[str]]:
    pstart, _ = locate(lines, [ROOT, "profiles", "windows"])
    lines = replace_line(lines, pstart, open_header(lines[pstart]))
    pend = block_end(lines, pstart)
    bidx = find_child(lines, pstart, pend, "buckets")
    if bidx < 0:
        pad = " " * child_indent(lines, pstart, pend)
        bidx = pstart + 1
        lines = lines[:bidx] + [f"{pad}buckets:"] + lines[bidx:]
    lines = replace_line(lines, bidx, open_header(lines[bidx]))
    added: list[str] = []
    for name, url in buckets.items():
        if not isinstance(name, str) or not isinstance(url, str) or not url.strip():
            raise SpecError(f"buckets must map a bucket name to a source URL string, got {name!r}: {url!r}")
        bend = block_end(lines, bidx)
        if find_child(lines, bidx, bend, name) >= 0:
            continue
        pad = " " * child_indent(lines, bidx, bend)
        pos = append_pos(lines, bidx, bend)
        lines = lines[:pos] + [f"{pad}{name}:", f"{pad}  source: {scalar(url)}"] + lines[pos:]
        added.append(name)
    return lines, added


def apply_spec(text: str, spec: dict, replace: bool = False) -> tuple[str, dict]:
    package = spec.get("package") or {}
    key = package.get("key")
    if not key or not isinstance(key, str):
        raise SpecError("spec.package.key is required")
    lines = text.split("\n")
    report: dict = {"package": key}
    lines, report["package_status"] = upsert_package(lines, key, package.get("entry") or {}, replace)
    if spec.get("taps"):
        lines, report["taps_added"] = ensure_taps(lines, list(spec["taps"]), spec.get("taps_profile") or "unixlike")
    if spec.get("buckets"):
        lines, report["buckets_added"] = ensure_buckets(lines, dict(spec["buckets"]))
    group = spec.get("group")
    if group and group.get("name"):
        placement = group.get("placement") or "shared"
        lines, created, added = place_in_group(lines, group["name"], placement, key, group.get("profiles"))
        report["group"] = {"name": group["name"], "placement": placement, "created": created,
                           "added": added, "profiles": list(group.get("profiles") or []) if created else []}
    return "\n".join(lines), report


def show(text: str, key: str) -> dict:
    lines = text.split("\n")
    start, end = locate(lines, [ROOT, "packages"])
    idx = find_child(lines, start, end, key)
    result = {"key": key, "defined": idx >= 0, "stanza": lines[idx:block_end(lines, idx)] if idx >= 0 else [], "groups": [], "profiles": []}
    gstart, gend = locate(lines, [ROOT, "groups"])
    for gi, kind, gname in children(lines, gstart, gend):
        if kind != "key":
            continue
        for ci, ckind, cname in children(lines, gi, block_end(lines, gi)):
            if ckind == "item" and cname == key:
                result["groups"].append(gname)
            elif ckind == "key" and any(k == "item" and n == key for _, k, n in children(lines, ci, block_end(lines, ci))):
                result["groups"].append(f"{gname}.{cname}")
    pstart, pend = locate(lines, [ROOT, "profiles"])
    for pi, kind, pname in children(lines, pstart, pend):
        if kind != "key":
            continue
        pk = find_child(lines, pi, block_end(lines, pi), "packages")
        if pk >= 0 and any(k == "item" and n == key for _, k, n in children(lines, pk, block_end(lines, pk))):
            result["profiles"].append(pname)
    return result


def context(text: str) -> dict:
    data = check.load_yaml_text(text) or {}
    root = data.get(ROOT) or {}
    groups = {}
    for name, group in (root.get("groups") or {}).items():
        if group is None or group == {}:
            groups[name] = {"shape": "empty", "members": {}}
        elif isinstance(group, list):
            groups[name] = {"shape": "flat", "members": {"shared": group}}
        else:
            groups[name] = {"shape": "map", "members": {k: (v or []) for k, v in group.items()}}
    profiles = {}
    for name, profile in (root.get("profiles") or {}).items():
        profile = profile or {}
        profiles[name] = {"taps": profile.get("taps") or [], "groups": profile.get("groups") or [],
                          "buckets": sorted((profile.get("buckets") or {}).keys()), "packages": profile.get("packages") or []}
    bucket_map = ((root.get("profiles") or {}).get("windows") or {}).get("buckets") or {}
    return {
        "packages": sorted(root.get("packages") or {}),
        "groups": groups,
        "profiles": profiles,
        "taps": sorted({check.norm_tap(t) for p in profiles.values() for t in p["taps"] if isinstance(t, str)}),
        "buckets": {name: (value or {}).get("source") for name, value in bucket_map.items()},
        "preferredManagerOrder": root.get("preferedManagerOrder") or root.get("preferredManagerOrder") or {},
        "defaultManagers": root.get("defaultManagers") or {},
    }


# --------------------------------------------------------------------------- cli

def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_atomically(path: str, text: str) -> None:
    """Write via a temp file in the same directory and rename, so a crash never leaves a half-written registry."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".packages-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def cmd_apply(args) -> int:
    spec_text = sys.stdin.read() if args.spec == "-" else read_text(args.spec)
    try:
        spec = json.loads(spec_text)
    except ValueError as exc:
        print(f"apply.py: spec is not valid JSON: {exc}", file=sys.stderr)
        return 2
    old = read_text(args.file)
    try:
        new, report = apply_spec(old, spec, replace=args.replace)
    except KeyExists as exc:
        print(f"apply.py: package `{exc}` already exists; run `show {exc}` or pass --replace", file=sys.stderr)
        return 3
    except SpecError as exc:
        print(f"apply.py: {exc}", file=sys.stderr)
        return 2

    rel = os.path.relpath(args.file)
    if rel.startswith(".."):
        rel = args.file
    label = rel.lstrip("/")
    diff = difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{label}", f"b/{label}")
    sys.stdout.writelines(diff)
    if old == new:
        print("apply.py: nothing to change")

    try:
        problems = check.new_findings(check.run_checks(new), check.run_checks(old))
    except RuntimeError as exc:
        problems = []
        report["validation"] = f"skipped: {exc}"
    else:
        report["validation"] = [str(p) for p in problems] or "no new findings"
    errors = [p for p in problems if p.level == "error"]

    print()
    print(json.dumps(report, indent=2))
    if errors and not args.force:
        print("apply.py: refusing to write; the change introduces structural errors (see validation). Use --force to override.", file=sys.stderr)
        return 1
    if args.dry_run:
        print("apply.py: dry run, file not written")
        return 0
    write_atomically(args.file, new)
    print(f"apply.py: wrote {rel}")
    return 0


def cmd_show(args) -> int:
    try:
        result = show(read_text(args.file), args.key)
    except SpecError as exc:
        print(f"apply.py: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    if result["defined"]:
        print("\n".join(result["stanza"]))
    else:
        print(f"`{args.key}` is not defined under packages")
    print(f"groups: {', '.join(result['groups']) or '(none)'}")
    print(f"profile packages lists: {', '.join(result['profiles']) or '(none)'}")
    return 0


def cmd_context(args) -> int:
    try:
        print(json.dumps(context(read_text(args.file)), indent=2))
    except (RuntimeError, ValueError) as exc:
        print(f"apply.py: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", dest="file_global", default=None, help=f"packages file (default {DEFAULT_FILE})")
    # --file is accepted both before and after the subcommand; people reach for either.
    file_opt = argparse.ArgumentParser(add_help=False)
    file_opt.add_argument("--file", dest="file_local", default=None, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    p_apply = sub.add_parser("apply", help="apply a JSON spec", parents=[file_opt])
    p_apply.add_argument("spec", help="spec path, or - for stdin")
    p_apply.add_argument("--dry-run", action="store_true", help="print the diff and report without writing")
    p_apply.add_argument("--replace", action="store_true", help="replace the stanza if the key exists")
    p_apply.add_argument("--force", action="store_true", help="write even if new structural errors are introduced")
    p_apply.set_defaults(func=cmd_apply)
    p_show = sub.add_parser("show", help="show a package's stanza and memberships", parents=[file_opt])
    p_show.add_argument("key")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)
    p_ctx = sub.add_parser("context", help="describe groups, profiles, taps, buckets", parents=[file_opt])
    p_ctx.set_defaults(func=cmd_context)
    args = parser.parse_args(argv)
    args.file = args.file_local or args.file_global or DEFAULT_FILE
    try:
        return args.func(args)
    except OSError as exc:
        print(f"apply.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
