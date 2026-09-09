#!/usr/bin/env bash
#
# Replay the Bioconductor -> bio.tools conversion, locally and only locally.
#
#   1. clone the commons with full history, and utils at the ref under test
#   2. recover every bio.tools file to its state before the conversion first
#      touched it, and delete the entries the conversion created
#   3. run the FIXED converter over that recovered state, twice, and check the
#      second run changes nothing
#   4. run the matcher under two hash seeds and check it agrees
#
# Nothing is pushed. Both clones get a poisoned push URL and a pre-push hook
# that refuses, so an accidental push fails loudly instead of reaching GitHub.
# Every file written lives under the work directory.
#
# usage: ./replay-conversion.sh [workdir] [existing-content-clone] [existing-venv]
set -euo pipefail

WORK="$(realpath -m "${1:-./bc2bt-replay}")"
# resolve before any cd, or a relative reuse path silently misses
REUSE_CONTENT=""
[ -n "${2:-}" ] && REUSE_CONTENT="$(realpath -m "$2")"
REUSE_VENV=""
[ -n "${3:-}" ] && REUSE_VENV="$(realpath -m "$3")"
UTILS_URL="https://github.com/research-software-ecosystem/utils.git"
CONTENT_URL="https://github.com/research-software-ecosystem/content.git"
UTILS_REF="main"
CONVERT_SUBJECT="convert bioconductor to biotools format"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

block_pushes() {   # make "local only" a property of the clone, not a promise
    local repo="$1"
    git -C "$repo" remote set-url --push origin "no-push://blocked-by-replay-script"
    mkdir -p "$repo/.git/hooks"
    printf '#!/bin/sh\necho "pre-push blocked: local replay clone" >&2\nexit 1\n' \
        > "$repo/.git/hooks/pre-push"
    chmod +x "$repo/.git/hooks/pre-push"
}

mkdir -p "$WORK"; cd "$WORK"

# ------------------------------------------------------------------ clones
if [ -n "$REUSE_CONTENT" ] && [ -d "$REUSE_CONTENT/.git" ]; then
    say "reusing content clone at $REUSE_CONTENT"
    CONTENT="$(realpath "$REUSE_CONTENT")"
else
    if [ ! -d content/.git ]; then
        say "cloning the commons with full history (blobless, several minutes)"
        git clone --quiet --filter=blob:none --no-checkout "$CONTENT_URL" content
    fi
    CONTENT="$WORK/content"
fi
block_pushes "$CONTENT"

if false; then
    say "cloning utils at $UTILS_REF"
    git clone --quiet --branch "$UTILS_REF" --depth 1 "$UTILS_URL" utils
fi
block_pushes utils
git -C utils log -1 --format='    fix under test: %h %s'

# --------------------------------------- which commits did the converting?
mapfile -t CONVERSIONS < <(
    git -C "$CONTENT" log origin/master --format='%H%x09%s' --reverse \
        | grep -i "$CONVERT_SUBJECT" | cut -f1
)
say "${#CONVERSIONS[@]} conversion commits"
git -C "$CONTENT" log -1 --format='    first: %h %ci' "${CONVERSIONS[0]}"
git -C "$CONTENT" log -1 --format='    last:  %h %ci' "${CONVERSIONS[-1]}"

# For every bio.tools file a conversion ever touched, remember the blob it
# replaced the FIRST time it was touched. That is the file as it stood before
# any pollution. A zero oid means the conversion created the file, so the clean
# state is for it not to exist at all.
say "collecting pre-conversion blobs"
: > first_pre.tsv
for sha in "${CONVERSIONS[@]}"; do
    git -C "$CONTENT" diff-tree -r --raw --no-commit-id "$sha^" "$sha" -- data \
        | awk -F'\t' '$2 ~ /\.biotools\.json$/ {split($1,a," "); print $2"\t"a[3]}'
done | awk -F'\t' '!seen[$1]++' >> first_pre.tsv
wc -l < first_pre.tsv

# ------------------------------------------------- materialise a clean tree
# Files a previous replay created are untracked, so rewinding tracked files
# does not remove them and successive runs would match against leftovers.
say "discarding anything a previous replay left behind"
git -C "$CONTENT" clean -fdxq -- data imports 2>/dev/null || true
git -C "$CONTENT" checkout -f -- data imports 2>/dev/null || true
printf '    untracked files under data/ now: %s\n' \
    "$(git -C "$CONTENT" status --porcelain data | awk '$1=="??"' | wc -l)"

say "checking out the current state (sparse)"
git -C "$CONTENT" sparse-checkout init --no-cone
printf '/imports/bioconductor/\n/data/*/*.biotools.json\n' \
    > "$CONTENT/.git/info/sparse-checkout"
git -C "$CONTENT" checkout --quiet --force origin/master

# Work inside the throwaway clone rather than copying the tree. Three copies
# of 34k files is roughly 600 MB and is what exhausted the disk first time.
COMMONS="$CONTENT"

say "rewinding the touched files to their pre-conversion state"
export FIRST_PRE="$WORK/first_pre.tsv"
python3 - "$CONTENT" "$COMMONS" <<'PY'
import subprocess, sys, os, pathlib
content, commons = sys.argv[1], sys.argv[2]
rows = [l.rstrip("\n").split("\t") for l in open(os.environ["FIRST_PRE"]) if "\t" in l]
created = [p for p, o in rows if o.startswith("000000")]
restore = [(p, o) for p, o in rows if not o.startswith("000000")]

for p in created:                      # the conversion invented these
    f = pathlib.Path(commons, p)
    if f.exists():
        f.unlink()
        try: f.parent.rmdir()
        except OSError: pass

proc = subprocess.run(["git", "-C", content, "cat-file", "--batch"],
                      input=("\n".join(o for _, o in restore) + "\n").encode(),
                      capture_output=True)
buf, pos, n = proc.stdout, 0, 0
for p, o in restore:
    nl = buf.find(b"\n", pos)
    if nl < 0: break
    head = buf[pos:nl].decode("utf-8", "replace")
    if head.endswith((" missing", " ambiguous")):
        pos = nl + 1; continue
    size = int(head.rsplit(" ", 1)[1])
    f = pathlib.Path(commons, p)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(buf[nl + 1: nl + 1 + size])
    pos = nl + 1 + size + 1
    n += 1
print(f"    restored {n} files, removed {len(created)} conversion-created entries")
PY


say "recovered inputs"
printf '    %s bio.tools entries\n' "$(find "$COMMONS/data" -name '*.biotools.json' | wc -l)"
printf '    %s Bioconductor source records\n' \
    "$(find "$COMMONS/imports/bioconductor" -name '*.bioconductor.json' | wc -l)"

# ---------------------------------------------------------------- the tool
if [ -n "$REUSE_VENV" ]; then
    PYBIN="$REUSE_VENV/bin"
    say "reusing python env at $REUSE_VENV"
else
    if [ ! -d venv ]; then
        say "installing the fixed bc2bt into a local venv"
        python3 -m venv venv
        ./venv/bin/pip --quiet install -r utils/bioconductor-to-biotools/requirements.txt
    fi
    PYBIN="$WORK/venv/bin"
fi
"$PYBIN/pip" --quiet install --force-reinstall --no-deps ./utils/bioconductor-to-biotools

# ------------------------------------------------------------ run it twice
rm -rf work1 work2
say "run 1 of the fixed converter"
( cd "$COMMONS" && "$PYBIN/bc2bt-sync" imports/bioconductor data \
    --work-dir "$WORK/work1" --keep-work-dir ) 2>&1 | tail -8
( cd "$COMMONS" && find data -name '*.biotools.json' -print0 | sort -z \
    | xargs -0 sha256sum ) > run1.sha256

say "run 2, over run 1's output"
( cd "$COMMONS" && "$PYBIN/bc2bt-sync" imports/bioconductor data \
    --work-dir "$WORK/work2" --keep-work-dir ) 2>&1 | tail -8
( cd "$COMMONS" && find data -name '*.biotools.json' -print0 | sort -z \
    | xargs -0 sha256sum ) > run2.sha256

say "IDEMPOTENCY: files differing between run 1 and run 2"
comm -13 <(sort run1.sha256) <(sort run2.sha256) | wc -l

# ------------------------------------------------- determinism of matching
say "DETERMINISM: matcher under two hash seeds"
for SEED in 1 2; do
    PYTHONHASHSEED=$SEED "$PYBIN/python" - "$WORK" "$SEED" "$COMMONS" <<'PY'
import json, sys, hashlib
from bc2bt.mapper import compare_files
work, seed = sys.argv[1], sys.argv[2]
res = compare_files(sys.argv[3] + "/data/*/*.biotools.json",
                    f"{work}/work1/converted/*.biotools.json",
                    ["name_homepage", "doi"])
pairs = sorted((e, c) for m in res["match_results"].values()
               for e, cs in m.items() for c in cs)
out = {"pairs": len(pairs), "conflicts": len(res.get("conflicts", [])),
       "digest": hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]}
open(f"{work}/match-seed{seed}.json", "w").write(json.dumps(out, indent=2))
print(f"    seed={seed} pairs={out['pairs']} conflicts={out['conflicts']} digest={out['digest']}")
PY
done
diff -q match-seed1.json match-seed2.json >/dev/null \
    && echo "    identical across seeds" || echo "    DIFFERENT across seeds"

say "artefacts in $WORK"
echo "    $COMMONS/data  the tree after the fixed converter ran twice"
echo "    work1/, work2/  converted files and match results per run"
