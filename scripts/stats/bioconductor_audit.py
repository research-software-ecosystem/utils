#!/usr/bin/env python3
"""Audit what the Bioconductor -> bio.tools conversion did to the commons.

Answers two questions with exact counts rather than estimates:

  duplicates    how many bioconductor-<pkg> entries duplicate an entry that was
                already in the commons (the vsclust / bioconductor-vsclust
                case), and whether that counterpart was also rewritten;

  publications  how many entries had their publication list overwritten, split
                by whether a real paper DOI was displaced by the Bioconductor
                package placeholder 10.18129/B9.bioc.<pkg> (the PolySTest case).

Method notes, each one a wrong turn worth not repeating:

  * The before-state comes from git history, never from the
    *.biotools.json.backup files. Those are rewritten on every run, so they
    hold only the last run's delta and show a no-op once a value has settled.
  * 10.18129/B9.bioc.* is a real, registered DOI. The harm is substitution, so
    entries are classified by what the placeholder displaced, not by format.
  * biotoolsID case does not match the folder name (folder polystest, ID
    PolySTest), so identifier comparison is case-insensitive throughout.
  * A shared paper DOI does not prove two records describe the same software --
    that assumption is what caused the PolySTest overwrite. Here it is only
    corroborating evidence, never the primary duplicate signal.
  * A tool can be rewritten by several conversion commits in a row, because the
    import in between restores it from the registry. Transitions are collapsed
    per tool: earliest pre-state against latest post-state.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BIOC_PREFIX = "bioconductor-"
PLACEHOLDER = re.compile(r"^10\.18129/B9\.bioc\.", re.I)
CONVERT_SUBJECT = "convert bioconductor to biotools format"


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    ).stdout


def list_tree(repo, ref="origin/master"):
    """Every data/ path at HEAD, from the tree alone -- no file contents."""
    folders = defaultdict(set)
    for path in git(repo, "ls-tree", "-r", ref, "--name-only").splitlines():
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "data":
            folders[parts[1]].add(parts[2])
    return folders


def stage0(folders):
    """Duplicate pairs and rewritten entries, from names only."""
    lower = {name.lower(): name for name in folders}

    def rewritten(name):
        return any(f.endswith(".biotools.json.backup") for f in folders[name])

    def is_biotools_entry(name):
        """A folder is a bio.tools entry only if it holds a bio.tools record.

        Most bioconductor-* folders are not conversion output at all: Bioconda
        names its Bioconductor packages bioconductor-<pkg>, so those folders
        predate the conversion and contain only bioconda/biocontainers/oeb
        files. Counting them as duplicates overstates the damage several-fold.
        """
        return f"{name}.biotools.json" in folders[name]

    pairs, orphans, packaging_only = [], [], []
    for name in sorted(folders):
        if not name.startswith(BIOC_PREFIX):
            continue
        if not is_biotools_entry(name):
            packaging_only.append(name)
            continue
        counterpart = lower.get(name[len(BIOC_PREFIX):].lower())
        if counterpart and counterpart != name and is_biotools_entry(counterpart):
            pairs.append((name, counterpart))
        else:
            orphans.append(name)
    rewritten_plain = sorted(
        n for n in folders if not n.startswith(BIOC_PREFIX) and rewritten(n)
    )
    return pairs, orphans, rewritten_plain, rewritten, packaging_only


def conversion_commits(repo, ref="origin/master"):
    out = []
    for line in git(repo, "log", ref, "--format=%H%x09%ci%x09%s", "--reverse").splitlines():
        sha, date, subject = line.split("\t", 2)
        if subject.strip().lower().startswith(CONVERT_SUBJECT):
            out.append((sha, date[:16]))
    return out


def touched_paths(repo, shas):
    """First pre-conversion and last post-conversion blob id per path.

    --raw reports both object ids without reading content, so the costly part
    is deferred to a single batched checkout.
    """
    first_pre, last_post = {}, {}
    for sha in shas:
        raw = git(repo, "diff-tree", "-r", "--raw", "--no-commit-id",
                  f"{sha}^", sha, "--", "data", check=False)
        for line in raw.splitlines():
            if "\t" not in line:
                continue
            meta, path = line.split("\t", 1)
            if not path.endswith(".biotools.json"):
                continue
            bits = meta.split()
            if len(bits) >= 5:
                first_pre.setdefault(path, bits[2])
                last_post[path] = bits[3]
    return first_pre, last_post


def batch_read(repo, keys):
    """Read many blobs in one git cat-file --batch pass.

    Keys are either object ids (from diff-tree --raw) or rev:path strings.
    Reading by object id is what makes the before-state exact: it is the very
    blob the conversion commit replaced, so no baseline commit has to be
    chosen and files that did not yet exist simply come back missing.
    """
    keys = list(keys)
    if not keys:
        return {}
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=("\n".join(keys) + "\n").encode(),
        capture_output=True, check=False,
    )
    out, pos, result = proc.stdout, 0, {}
    for key in keys:
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        header = out[pos:nl].decode("utf-8", "replace")
        if header.endswith((" missing", " ambiguous")):
            pos = nl + 1
            continue
        try:
            size = int(header.rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            pos = nl + 1
            continue
        blob = out[nl + 1: nl + 1 + size]
        pos = nl + 1 + size + 1
        try:
            result[key] = json.loads(blob.decode("utf-8", "replace"))
        except Exception:
            pass
    return result



def sparse_read(repo, paths, ref):
    """Materialise these paths at ref in one batched fetch, then read them.

    A partial clone fetches lazily, one object per request, which for a few
    thousand blobs is minutes of round trips. A sparse checkout asks for the
    whole set at once, which is seconds.
    """
    paths = sorted(set(paths))
    git(repo, "sparse-checkout", "init", "--no-cone", check=False)
    proc = subprocess.run(
        ["git", "-C", str(repo), "sparse-checkout", "set", "--stdin"],
        input=("\n".join("/" + p for p in paths) + "\n").encode(),
        capture_output=True, check=False,
    )
    git(repo, "checkout", "-f", ref, check=False)
    snap = {}
    for p in paths:
        f = repo / p
        if f.exists():
            try:
                snap[p] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return snap


ZERO_OID = "0" * 40


def dois(record):
    return [
        (pub.get("doi") or "").strip()
        for pub in ((record or {}).get("publication") or [])
        if (pub.get("doi") or "").strip()
    ]


def has_metadata(record):
    return any(pub.get("metadata")
               for pub in ((record or {}).get("publication") or []))


def classify(before, after):
    if before is None or after is None:
        return "not_in_both_snapshots"
    bset = {d.lower() for d in dois(before)}
    aset = {d.lower() for d in dois(after)}
    b_real = {d for d in bset if not PLACEHOLDER.match(d)}
    a_real = {d for d in aset if not PLACEHOLDER.match(d)}
    if not bset and aset:
        return "added"
    if bset == aset:
        if has_metadata(before) and not has_metadata(after):
            return "metadata_stripped"
        return "unchanged"
    if b_real and not a_real:
        return "real_displaced_by_placeholder"
    if b_real - a_real:
        return "real_doi_lost"
    return "other_change"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--report-dir", default="bioconductor-audit")
    ap.add_argument("--ref", default="origin/master",
                    help="ref to treat as current state (default: origin/master)")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    out = Path(args.report_dir); out.mkdir(parents=True, exist_ok=True)

    print("stage 0: reading tree at HEAD ...", flush=True)
    folders = list_tree(repo, args.ref)
    pairs, orphans, rewritten_plain, rewritten, packaging_only = stage0(folders)
    both = [(a, b) for a, b in pairs if rewritten(b)]
    dup_only = [(a, b) for a, b in pairs if not rewritten(b)]
    pure = sorted(set(rewritten_plain) - {b for _, b in pairs})
    print(f"  {len(folders):,} folders, {len(pairs):,} duplicate pairs", flush=True)

    commits = conversion_commits(repo, args.ref)
    print(f"stage 2: {len(commits)} conversion commits "
          f"({commits[0][1]} .. {commits[-1][1]})", flush=True)
    first_pre, _ = touched_paths(repo, [s for s, _ in commits])
    paths = sorted(first_pre)
    print(f"  {len(paths):,} .biotools.json files touched", flush=True)

    # "before" = the exact blob each conversion commit replaced, by object id.
    pre_keys = {p: o for p, o in first_pre.items() if o != ZERO_OID}
    pre_blobs = batch_read(repo, set(pre_keys.values()))
    before = {p: pre_blobs[o] for p, o in pre_keys.items() if o in pre_blobs}
    print(f"  pre-conversion blobs resolved: {len(before):,}/{len(pre_keys):,}", flush=True)

    # "after" = the current state at ref, so the verdict is about today, not
    # about an intermediate run that a later import may have undone.
    pair_paths = [f"data/{n}/{n}.biotools.json" for pr in pairs for n in pr]
    snap = sparse_read(repo, list(first_pre) + pair_paths, args.ref)
    after = {p: snap[p] for p in first_pre if p in snap}
    current = {n: snap[f"data/{n}/{n}.biotools.json"]
               for pr in pairs for n in pr
               if f"data/{n}/{n}.biotools.json" in snap}
    print(f"  current records read: {len(after):,} touched, "
          f"{len(current):,} pair records", flush=True)

    classes = defaultdict(list); rows = []
    for p in paths:
        tool = p.split("/")[1]
        b, a = before.get(p), after.get(p)
        kind = classify(b, a)
        classes[kind].append(tool)
        if kind in ("real_displaced_by_placeholder", "real_doi_lost",
                    "metadata_stripped", "other_change"):
            rows.append({"tool": tool, "class": kind,
                         "dois_before": ";".join(dois(b)),
                         "dois_after": ";".join(dois(a)),
                         "metadata_before": has_metadata(b),
                         "metadata_after": has_metadata(a)})
    cols = ["tool", "class", "dois_before", "dois_after",
            "metadata_before", "metadata_after"]
    with open(out / "publications.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)

    def rec(n): return current.get(n)
    dup_rows = []
    for bioc, plain in pairs:
        rb, rp = rec(bioc), rec(plain)
        nb = ((rb or {}).get("name") or "").strip().lower()
        npl = ((rp or {}).get("name") or "").strip().lower()
        db = {d.lower() for d in dois(rb) if not PLACEHOLDER.match(d.lower())}
        dp = {d.lower() for d in dois(rp) if not PLACEHOLDER.match(d.lower())}
        hb = ((rb or {}).get("homepage") or "").split("://")[-1].rstrip("/")
        hp = ((rp or {}).get("homepage") or "").split("://")[-1].rstrip("/")
        sig = []
        if nb and nb == npl: sig.append("name")
        if db & dp: sig.append("doi")
        if hb and hb == hp: sig.append("homepage")
        dup_rows.append({
            "bioconductor_entry": bioc, "counterpart": plain,
            "counterpart_rewritten": rewritten(plain),
            "evidence": "+".join(sig) or "stem_only",
            "tier": "confirmed" if len(sig) >= 2 else ("probable" if sig else "stem_only"),
            "bioc_topics": len(((rb or {}).get("topic") or [])),
            "counterpart_topics": len(((rp or {}).get("topic") or [])),
            "counterpart_functions": len(((rp or {}).get("function") or [])),
        })
    with open(out / "duplicates.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(dup_rows[0])); w.writeheader(); w.writerows(dup_rows)

    tiers = defaultdict(int)
    for r in dup_rows: tiers[r["tier"]] += 1
    ann_loss = sum(1 for r in dup_rows
                   if r["counterpart_topics"] > 0 and r["bioc_topics"] == 0)

    summary = {
        "tool_folders": len(folders),
        "conversion_commits": [{"sha": s, "date": d} for s, d in commits],
        "files_touched_by_conversion": len(paths),
        "duplicates": {
            "bioconductor_entries": len(pairs) + len(orphans),
            "with_counterpart": len(pairs),
            "counterpart_also_rewritten": len(both),
            "counterpart_untouched": len(dup_only),
            "no_counterpart": len(orphans),
            "bioconductor_prefixed_packaging_only": len(packaging_only),
            "tiers": dict(tiers),
            "annotated_counterpart_empty_twin": ann_loss,
        },
        "rewritten_entries": {
            "pre_existing_total": len(rewritten_plain),
            "without_bioconductor_twin": len(pure),
        },
        "publications": {k: len(v) for k, v in
                         sorted(classes.items(), key=lambda kv: -len(kv[1]))},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== duplicates ===")
    print(f"  bioconductor-* entries               {len(pairs)+len(orphans):>7,}")
    print(f"    with a counterpart                 {len(pairs):>7,}")
    print(f"      counterpart also rewritten       {len(both):>7,}")
    print(f"      counterpart untouched            {len(dup_only):>7,}  (vsclust class)")
    print(f"    no counterpart, genuinely new      {len(orphans):>7,}")
    print(f"  bioconductor-* folders that are NOT bio.tools entries "
          f"{len(packaging_only):>7,}\n    (Bioconda/BioContainers package folders, not conversion output)")
    print("  evidence tiers: " + ", ".join(f"{k}={v:,}" for k, v in sorted(tiers.items())))
    print(f"  annotated counterpart, empty twin    {ann_loss:>7,}")
    print("\n=== rewritten pre-existing entries ===")
    print(f"  total                                {len(rewritten_plain):>7,}")
    print(f"  without a bioconductor-* twin        {len(pure):>7,}  (PolySTest class)")
    print("\n=== publication transitions ===")
    for k, v in sorted(classes.items(), key=lambda kv: -len(kv[1])):
        print(f"  {k:<34} {len(v):>7,}")
    print(f"\nwrote {out}/summary.json, duplicates.csv, publications.csv")


if __name__ == "__main__":
    main()
