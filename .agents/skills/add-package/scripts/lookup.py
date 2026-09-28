#!/usr/bin/env python3
"""Resolve a package name across Homebrew (formula and cask), winget, scoop and PyPI.

Usage
  lookup.py NAME [--manager brew|cask|winget|scoop|pipx|msstore] [--os darwin|windows]
                 [--tap USER/REPO] [--winget-id ID] [--bucket NAME[=OWNER/REPO]] [--refresh]

Prints one JSON document and never installs or taps anything. Sources, in order of trust:
  Homebrew  formulae.brew.sh API for core formulae/casks; `brew info` (when installed) for
            taps already on this machine; the tap's GitHub repo when you pass --tap or a
            full `user/repo/name` (checked as user/homebrew-repo, Formula/ or Casks/).
  winget    the pre-indexed source database that `winget search` itself reads
            (cdn.winget.microsoft.com/cache/source.msix, cached locally for a day), with the
            winget-pkgs manifest tree on GitHub as a fallback verifier for --winget-id.
  scoop     `bucket/<name>.json` in the official buckets (plus any --bucket), and a fuzzy pass
            over the main and extras bucket trees when nothing matches exactly.
  PyPI      existence check for a pipx candidate.

GitHub calls go through `gh api` when available (authenticated, 5000 req/h), else anonymous HTTPS.
The `suggested_*` fields apply the registry's rules (see references/schema.md); read `notes`
before trusting them, they flag ambiguity that needs a human or a second look.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

USER_AGENT = "add-package-skill/1.0 (+https://github.com/cawaltrip/dotfiles)"
BREW_API = "https://formulae.brew.sh/api"
BREW_CORE_TAPS = {"homebrew/core", "homebrew/cask"}
WINGET_INDEX_URL = "https://cdn.winget.microsoft.com/cache/source.msix"
WINGET_INDEX_TTL_SECONDS = 24 * 3600
WINGET_PKGS_REPO = "microsoft/winget-pkgs"
OFFICIAL_BUCKETS = {
    "main": "ScoopInstaller/Main",
    "extras": "ScoopInstaller/Extras",
    "versions": "ScoopInstaller/Versions",
    "nerd-fonts": "ScoopInstaller/Nerd-Fonts",
    "java": "ScoopInstaller/Java",
    "games": "ScoopInstaller/Games",
    "nonportable": "ScoopInstaller/Nonportable",
    "php": "ScoopInstaller/PHP",
    "sysinternals": "ScoopInstaller/Sysinternals",
}
FUZZY_BUCKETS = ("main", "extras")
DEFAULT_WINDOWS_ORDER = ["winget", "scoop", "pipx"]
WINDOWS_MANAGERS = {"winget", "scoop", "pipx", "msstore"}
DARWIN_MANAGERS = {"brew", "cask"}
HTTP_TIMEOUT_SECONDS = 30
INDEX_DOWNLOAD_TIMEOUT_SECONDS = 180
RESULT_LIMIT = 10


# --------------------------------------------------------------------------- plumbing

def cache_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "add-package")
    os.makedirs(path, exist_ok=True)
    return path


def http_get(url: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT_SECONDS) -> tuple[int, bytes]:
    """(status, body). Network failures come back as status 0 so callers can degrade instead of crash."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b""


def http_json(url: str, headers: dict | None = None):
    status, body = http_get(url, headers)
    if status != 200:
        return status, None
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


def gh_api(path: str):
    """GitHub REST GET -> (status, json|None). `gh` first (authenticated), anonymous HTTPS as fallback."""
    if shutil.which("gh"):
        proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if proc.returncode == 0:
            try:
                return 200, json.loads(proc.stdout)
            except ValueError:
                return 200, None
        if "404" in proc.stderr or "Not Found" in proc.stderr:
            return 404, None
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return http_json(f"https://api.github.com/{path}", headers)


# --------------------------------------------------------------------------- homebrew

def brew_split(name: str) -> tuple[str | None, str]:
    """'user/repo/name' -> ('user/repo', 'name'); 'name' -> (None, 'name')."""
    parts = name.split("/")
    return ("/".join(parts[:2]), parts[-1]) if len(parts) >= 3 else (None, name)


def brew_record(kind: str, data: dict, source: str) -> dict:
    deprecated = bool(data.get("deprecated") or data.get("disabled"))
    if kind == "formula":
        return {"name": data["name"], "full_name": data["full_name"], "tap": data.get("tap") or "homebrew/core",
                "desc": data.get("desc"), "homepage": data.get("homepage"),
                "version": (data.get("versions") or {}).get("stable"), "deprecated": deprecated, "source": source}
    return {"token": data["token"], "full_token": data["full_token"], "tap": data.get("tap") or "homebrew/cask",
            "name": (data.get("name") or [None])[0], "desc": data.get("desc"), "homepage": data.get("homepage"),
            "version": data.get("version"), "deprecated": deprecated, "source": source}


def brew_api(kind: str, name: str) -> dict | None:
    status, data = http_json(f"{BREW_API}/{kind}/{name}.json")
    return brew_record(kind, data, "formulae.brew.sh") if status == 200 and data else None


def brew_cli(kind: str, name: str) -> dict | None:
    """`brew info --json=v2` covers taps already on this machine. Bare names only: a full name would auto-tap."""
    if not shutil.which("brew") or "/" in name:
        return None
    flag = "--formula" if kind == "formula" else "--cask"
    proc = subprocess.run(["brew", "info", "--json=v2", flag, name], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        items = json.loads(proc.stdout).get("formulae" if kind == "formula" else "casks") or []
    except ValueError:
        return None
    return brew_record(kind, items[0], "brew-cli") if items else None


def brew_tap_probe(kind: str, tap: str, name: str) -> dict | None:
    """Find Formula/<name>.rb or Casks/<name>.rb in the tap's GitHub repo without tapping it locally."""
    user, _, repo = tap.partition("/")
    if not repo:
        return None
    gh_repo = repo if repo.startswith("homebrew-") else f"homebrew-{repo}"
    short = repo[len("homebrew-"):] if repo.startswith("homebrew-") else repo
    letter = name[0].lower()
    if kind == "formula":
        paths = [f"Formula/{name}.rb", f"Formula/{letter}/{name}.rb", f"HomebrewFormula/{name}.rb", f"{name}.rb"]
    else:
        paths = [f"Casks/{name}.rb", f"Casks/{letter}/{name}.rb"]
    for path in paths:
        status, _ = gh_api(f"repos/{user}/{gh_repo}/contents/{path}")
        if status == 200:
            full = f"{user}/{short}/{name}"
            record = {"tap": f"{user}/{short}", "source": f"github:{user}/{gh_repo}/{path}", "deprecated": False}
            if kind == "formula":
                return {**record, "name": name, "full_name": full}
            return {**record, "token": name, "full_token": full}
    return None


def brew_search(name: str) -> dict | None:
    if not shutil.which("brew"):
        return None
    out = {}
    for kind, flag in (("formulae", "--formula"), ("casks", "--cask")):
        proc = subprocess.run(["brew", "search", flag, name], capture_output=True, text=True)
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip() and not ln.startswith("==>")]
        out[kind] = lines[:RESULT_LIMIT] if proc.returncode == 0 else []
    return out


def resolve_darwin(name: str, manager: str | None, tap: str | None) -> dict:
    tap_from_name, short = brew_split(name)
    tap = tap or tap_from_name
    formula = cask = None
    if manager in (None, "brew"):
        formula = brew_tap_probe("formula", tap, short) if tap else (brew_api("formula", short) or brew_cli("formula", short))
    if manager in (None, "cask"):
        cask = brew_tap_probe("cask", tap, short) if tap else (brew_api("cask", short) or brew_cli("cask", short))
    result: dict = {"formula": formula, "cask": cask}
    if not formula and not cask:
        result["search"] = brew_search(short)
    result["taps_required"] = sorted({r["tap"] for r in (formula, cask) if r and r.get("tap") not in BREW_CORE_TAPS})
    return result


# --------------------------------------------------------------------------- winget

def winget_index_path(refresh: bool = False) -> str | None:
    """Local copy of winget's pre-indexed SQLite database, refreshed daily. Stale beats absent."""
    db = os.path.join(cache_dir(), "winget-index.db")
    fresh = os.path.exists(db) and time.time() - os.path.getmtime(db) < WINGET_INDEX_TTL_SECONDS
    if fresh and not refresh:
        return db
    status, body = http_get(WINGET_INDEX_URL, timeout=INDEX_DOWNLOAD_TIMEOUT_SECONDS)
    if status != 200 or not body:
        return db if os.path.exists(db) else None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".msix") as tmp:
        tmp.write(body)
        msix = tmp.name
    try:
        with zipfile.ZipFile(msix) as archive:
            member = next((n for n in archive.namelist() if n.lower().endswith("index.db")), None)
            if not member:
                return db if os.path.exists(db) else None
            with archive.open(member) as src, open(db + ".tmp", "wb") as dst:
                shutil.copyfileobj(src, dst)
        os.replace(db + ".tmp", db)
    except (zipfile.BadZipFile, OSError):
        return db if os.path.exists(db) else None
    finally:
        os.unlink(msix)
    return db


WINGET_QUERY = """
SELECT DISTINCT i.id, n.name, COALESCE(m.moniker, '')
FROM manifest mf
JOIN ids i ON i.rowid = mf.id
JOIN names n ON n.rowid = mf.name
LEFT JOIN monikers m ON m.rowid = mf.moniker
WHERE lower(i.id) LIKE ? OR lower(n.name) LIKE ? OR lower(m.moniker) LIKE ?
"""


def winget_rank(term: str, row: tuple) -> tuple[int, str]:
    ident, name, moniker = (s.lower() for s in row)
    if ident == term:
        return 0, "id"
    if moniker == term:
        return 1, "moniker"
    if name == term:
        return 2, "name"
    if ident.endswith("." + term):
        return 3, "id-suffix"
    return 4, "fuzzy"


def winget_search(term: str, refresh: bool = False) -> list | None:
    db = winget_index_path(refresh)
    if not db:
        return None
    like = f"%{term.lower()}%"
    connection = sqlite3.connect(pathlib.Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = connection.execute(WINGET_QUERY, (like, like, like)).fetchall()
    finally:
        connection.close()
    ranked = sorted(((winget_rank(term.lower(), row), row) for row in rows), key=lambda x: (x[0][0], x[1][0].lower()))
    seen: set[str] = set()
    out = []
    for (_, match), (ident, name, moniker) in ranked:
        if ident in seen:
            continue
        seen.add(ident)
        out.append({"id": ident, "name": name, "moniker": moniker or None, "match": match})
        if len(out) >= RESULT_LIMIT:
            break
    return out


def winget_verify(ident: str, refresh: bool = False) -> dict:
    """Exact identifier check: the index first, then the winget-pkgs tree (the index lags new packages by hours)."""
    db = winget_index_path(refresh)
    if db:
        connection = sqlite3.connect(pathlib.Path(db).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            row = connection.execute("SELECT id FROM ids WHERE lower(id) = ?", (ident.lower(),)).fetchone()
        finally:
            connection.close()
        if row:
            return {"id": row[0], "verified": "index"}
    path = f"manifests/{ident[0].lower()}/{ident.replace('.', '/')}"
    status, data = gh_api(f"repos/{WINGET_PKGS_REPO}/contents/{path}")
    if status == 200 and isinstance(data, list) and any(d.get("type") == "dir" for d in data):
        return {"id": ident, "verified": "winget-pkgs"}
    return {"id": ident, "verified": False}


# --------------------------------------------------------------------------- scoop

def scoop_probe(name: str, buckets: dict) -> dict | None:
    """Exact `bucket/<name>.json` in each bucket, in order; the first hit wins."""
    for bucket, repo in buckets.items():
        status, data = gh_api(f"repos/{repo}/contents/bucket/{name}.json")
        if status != 200 or not isinstance(data, dict):
            continue
        manifest: dict = {}
        try:
            manifest = json.loads(base64.b64decode(data.get("content") or b"").decode("utf-8", "replace") or "{}")
        except ValueError:
            pass
        return {"name": name, "bucket": bucket, "source_url": f"https://github.com/{repo}",
                "description": manifest.get("description"), "homepage": manifest.get("homepage"), "version": manifest.get("version")}
    return None


def bucket_tree(repo: str) -> list[str]:
    status, data = gh_api(f"repos/{repo}/git/trees/HEAD:bucket")
    if status != 200 or not data:
        status, root = gh_api(f"repos/{repo}/contents")
        sha = next((e.get("sha") for e in (root or []) if isinstance(e, dict) and e.get("name") == "bucket"), None)
        if not sha:
            return []
        status, data = gh_api(f"repos/{repo}/git/trees/{sha}")
        if status != 200 or not data:
            return []
    return [e["path"][:-5] for e in data.get("tree", []) if e.get("path", "").endswith(".json")]


def scoop_fuzzy(term: str, buckets: dict) -> list:
    hits = []
    for bucket, repo in buckets.items():
        names = bucket_tree(repo)
        hits += [{"name": n, "bucket": bucket, "source_url": f"https://github.com/{repo}"} for n in names if term.lower() in n.lower()]
    hits.sort(key=lambda h: (not h["name"].lower().startswith(term.lower()), len(h["name"]), h["name"]))
    return hits[:RESULT_LIMIT]


def parse_bucket_arg(value: str) -> tuple[str, str]:
    name, _, repo = value.partition("=")
    name = name.strip().lower()
    repo = repo.strip() or OFFICIAL_BUCKETS.get(name) or f"ScoopInstaller/{name.capitalize()}"
    return name, repo


# --------------------------------------------------------------------------- pypi

def pypi_lookup(name: str) -> dict | None:
    status, data = http_json(f"https://pypi.org/pypi/{name}/json")
    if status != 200 or not data:
        return None
    info = data.get("info") or {}
    return {"name": info.get("name"), "summary": info.get("summary"), "version": info.get("version")}


# --------------------------------------------------------------------------- suggestion

def suggest_darwin(key: str, darwin: dict, manager: str | None) -> tuple[dict, bool, list[str]]:
    formula, cask = darwin.get("formula"), darwin.get("cask")
    notes: list[str] = []
    if manager == "cask":
        kind, info = "cask", cask
    elif manager == "brew":
        kind, info = "formula", formula
    else:
        kind, info = ("formula", formula) if formula else ("cask", cask)
        if formula and cask:
            notes.append(f"darwin: both a formula ({formula['full_name']}) and a cask ({cask['full_token']}) exist; "
                         "suggested the formula (CLI). Use the cask if the user wants the GUI app.")
    if not info:
        notes.append("darwin: nothing found in Homebrew. Leave darwin out of the entry and keep the package out of any group's "
                     "shared list (a missing OS key means 'brew install <key>', not 'skip').")
        return {}, False, notes
    ident = info["full_name"] if kind == "formula" else info["full_token"]
    if info.get("deprecated"):
        notes.append(f"darwin: {ident} is deprecated or disabled in Homebrew; confirm the user still wants it.")
    if kind == "formula":
        entry = {} if ident == key else {"darwin": ident}  # minimal form: the key itself is the default
    else:
        entry = {"darwin": {"cask": ident}}
    return entry, True, notes


def pick_winget(hits, notes: list[str]) -> str | None:
    """The single strong winget match, or None with a note saying what to disambiguate."""
    if hits is None:
        notes.append("windows: could not download the winget index; winget identifiers are unverified.")
        return None
    strong = [h for h in hits if h["match"] in ("id", "moniker", "name", "id-suffix")]
    if strong and (len(strong) == 1 or strong[0]["match"] in ("id", "moniker")):
        if strong[0]["match"] == "name":
            notes.append(f"windows: winget matched by display name only; double-check {strong[0]['id']}.")
        return strong[0]["id"]
    if len(strong) > 1:
        notes.append("windows: several winget packages match; pick one or pass --winget-id: " + ", ".join(h["id"] for h in strong[:5]))
    elif hits:
        notes.append("windows: only fuzzy winget matches: " + ", ".join(h["id"] for h in hits[:5]))
    return None


def resolve_windows(term: str, manager: str | None, order: list[str], winget_id: str | None, bucket_arg: str | None, refresh: bool):
    """Walk the Windows managers in preference order and stop at the first confirmed match.

    The registry holds exactly one Windows installer per package, so once a higher-priority
    manager has the package there is nothing to decide: lower-priority managers are not
    looked up (saves API calls) and are reported under `skipped` so they stay out of the report.
    `--manager` pins a single manager instead.
    """
    managers = [manager] if manager in WINDOWS_MANAGERS else list(order)
    result: dict = {"order": managers, "evaluated": [], "skipped": []}
    notes: list[str] = []
    entry: dict = {}
    buckets: dict = {}
    for index, mgr in enumerate(managers):
        result["evaluated"].append(mgr)
        if mgr == "winget":
            hits = winget_search(term, refresh)
            if winget_id:
                verified = winget_verify(winget_id, refresh)
                result["winget_verified"] = verified
                if verified["verified"]:
                    hits = [{"id": verified["id"], "name": None, "moniker": None, "match": "id"}] + [h for h in (hits or []) if h["id"].lower() != verified["id"].lower()]
                else:
                    notes.append(f"windows: `{winget_id}` was not found in the winget index or the winget-pkgs tree.")
            result["winget"] = hits
            ident = pick_winget(hits, notes)
            if ident:
                entry = {"windows": ident}
        elif mgr == "msstore":
            notes.append("windows: Microsoft Store ids cannot be looked up offline; take the 12-character id from the Store page URL and write it under msstore:.")
        elif mgr == "scoop":
            to_probe = dict([parse_bucket_arg(bucket_arg)]) if bucket_arg else dict(OFFICIAL_BUCKETS)
            hit = scoop_probe(term, to_probe)
            result["scoop"] = hit
            if hit:
                entry = {"windows": {"scoop": {"name": hit["name"], "source": hit["bucket"]}}}
                buckets = {hit["bucket"]: hit["source_url"]}
            else:
                fuzzy_buckets = to_probe if bucket_arg else {b: OFFICIAL_BUCKETS[b] for b in FUZZY_BUCKETS}
                result["scoop_search"] = scoop_fuzzy(term, fuzzy_buckets)
                if result["scoop_search"]:
                    notes.append("windows: no exact scoop app; similar names: " + ", ".join(f"{h['name']} ({h['bucket']})" for h in result["scoop_search"][:5]))
        elif mgr == "pipx":
            hit = pypi_lookup(term)
            result["pypi"] = hit
            if hit:
                entry = {"windows": {"pipx": hit["name"]}}
                notes.append(f"windows: PyPI has `{hit['name']}` ({hit.get('summary') or 'no summary'}); PyPI names collide, confirm it is the same tool before using pipx.")
        if entry:
            result["skipped"] = managers[index + 1:]
            break
    if not entry:
        notes.append("windows: nothing usable found on " + ", ".join(managers) + ". Leave windows out of the entry, keep the package out of shared lists, and consider a `# TODO` comment.")
    return result, entry, buckets, notes


def suggested_key(query: str, manager: str | None) -> str:
    if manager == "winget" and "." in query:
        return query.split(".")[-1].lower()
    return query.split("/")[-1].lower()


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="package name, formula, cask token, winget id/moniker, or scoop app name")
    parser.add_argument("--manager", choices=sorted(DARWIN_MANAGERS | WINDOWS_MANAGERS), help="which manager NAME belongs to")
    parser.add_argument("--os", choices=["darwin", "windows"], dest="only_os", help="look up one OS only")
    parser.add_argument("--tap", help="Homebrew tap (user/repo) to search instead of core")
    parser.add_argument("--winget-id", help="verify this exact winget identifier")
    parser.add_argument("--bucket", help="scoop bucket to search: NAME or NAME=OWNER/REPO")
    parser.add_argument("--order", default=",".join(DEFAULT_WINDOWS_ORDER), help="windows manager preference (default winget,scoop,pipx)")
    parser.add_argument("--refresh", action="store_true", help="re-download the winget index")
    args = parser.parse_args(argv)

    manager = args.manager
    only_os = args.only_os
    key = suggested_key(args.name, manager)
    result: dict = {"query": args.name, "manager": manager, "suggested_key": key}
    notes: list[str] = []
    entry: dict = {}
    buckets_needed: dict = {}
    availability = {"darwin": False, "windows": False}

    if only_os != "windows":
        darwin = resolve_darwin(args.name if manager in (None, "brew", "cask") else key, manager if manager in DARWIN_MANAGERS else None, args.tap)
        result["darwin"] = darwin
        darwin_entry, availability["darwin"], darwin_notes = suggest_darwin(key, darwin, manager if manager in DARWIN_MANAGERS else None)
        entry.update(darwin_entry)
        notes += darwin_notes

    if only_os != "darwin":
        term = args.name if manager in WINDOWS_MANAGERS else key
        order = [m.strip() for m in args.order.split(",") if m.strip()]
        windows, windows_entry, buckets_needed, windows_notes = resolve_windows(term, manager, order, args.winget_id, args.bucket, args.refresh)
        result["windows"] = windows
        entry.update(windows_entry)
        availability["windows"] = bool(windows_entry)
        notes += windows_notes

    if availability["darwin"] and availability["windows"]:
        placement = "shared"
    elif availability["darwin"] or availability["windows"]:
        placement = "darwin" if availability["darwin"] else "windows"
    else:
        placement = None
    result.update({
        "availability": availability,
        "suggested_entry": entry,
        "suggested_placement": placement,
        "taps_needed": (result.get("darwin") or {}).get("taps_required") or [],
        "buckets_needed": buckets_needed,
        "notes": notes,
    })
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
