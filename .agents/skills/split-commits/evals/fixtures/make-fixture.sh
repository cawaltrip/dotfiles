#!/usr/bin/env bash
# Build a scratch copy of this repo with a known mixed working-tree diff, for
# testing the split-commits skill without touching the real checkout.
#
#   make-fixture.sh <fixture-name> <dest-dir>
#
# Clones the repository at the commit in BASE_COMMIT into <dest-dir> (which must
# not exist), checks out `main` there, and applies <fixture-name>.patch as
# unstaged working-tree changes. New files in the patch end up untracked, exactly
# as if the user had just created them.
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
name=${1:?usage: make-fixture.sh <fixture-name> <dest-dir>}
dest=${2:?usage: make-fixture.sh <fixture-name> <dest-dir>}
patch="$here/$name.patch"

[[ -f $patch ]] || { echo "no such fixture: $patch" >&2; exit 2; }
[[ -e $dest ]] && { echo "destination exists: $dest" >&2; exit 2; }

base=$(<"$here/BASE_COMMIT")
src=$(git -C "$here" rev-parse --path-format=absolute --git-common-dir)

git clone -q --no-hardlinks "$src" "$dest"
git -C "$dest" checkout -q -B main "$base"
git -C "$dest" config user.name  >/dev/null 2>&1 || git -C "$dest" config user.name  "Fixture User"
git -C "$dest" config user.email >/dev/null 2>&1 || git -C "$dest" config user.email "fixture@example.com"
git -C "$dest" apply "$patch"

echo "fixture '$name' ready at $dest (base $(git -C "$dest" rev-parse --short HEAD))"
git -C "$dest" status --short
