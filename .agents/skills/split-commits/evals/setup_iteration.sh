#!/usr/bin/env bash
# Prepare a skill-creator iteration directory: one scratch clone per eval and
# configuration, eval_metadata.json with the grader's assertion texts, and the
# run-1/ symlink layout that scripts/aggregate_benchmark.py expects.
#
#   setup_iteration.sh <iteration-dir> [config ...]     (default configs: with_skill without_skill)
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
iter=${1:?usage: setup_iteration.sh <iteration-dir> [config ...]}
shift || true
configs=("$@")
[[ ${#configs[@]} -eq 0 ]] && configs=(with_skill without_skill)

mkdir -p "$iter"
python3 - "$here" "$iter" "${configs[@]}" <<'PYEOF'
import json, subprocess, sys, pathlib
here, iter_dir, *configs = sys.argv[1:]
here, iter_dir = pathlib.Path(here), pathlib.Path(iter_dir)
evals = json.loads((here / "evals.json").read_text())["evals"]
for e in evals:
    d = iter_dir / f"eval-{e['id']}-{e['name']}"
    d.mkdir(parents=True, exist_ok=True)
    texts = json.loads(subprocess.check_output(["python3", str(here / "grade.py"), "--list", e["name"]]))
    (d / "eval_metadata.json").write_text(json.dumps({
        "eval_id": e["id"], "eval_name": e["name"], "prompt": e["prompt"],
        "fixture": e["fixture"], "assertions": texts}, indent=2) + "\n")
    for cfg in configs:
        run = d / cfg
        (run / "outputs").mkdir(parents=True, exist_ok=True)
        (run / "run-1").mkdir(exist_ok=True)
        for f in ("grading.json", "timing.json"):
            link = run / "run-1" / f
            if not link.is_symlink():
                link.symlink_to(f"../{f}")
        if not (run / "repo").exists():
            subprocess.run([str(here / "fixtures/make-fixture.sh"), e["fixture"], str(run / "repo")],
                           check=True, stdout=subprocess.DEVNULL)
        print(f"{d.name}/{cfg}: repo ready, prompt -> {e['prompt'].replace('{{REPO}}', str(run / 'repo'))[:60]}...")
PYEOF
