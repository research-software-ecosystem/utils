#!/usr/bin/env python3
"""Per-field report on the entries the Bioconductor conversion rewrote.

For every bio.tools entry that already existed before the conversion, compare
the pre-conversion record against the current one, field by field, and say how
often each field was added to, replaced, or emptied -- then how many of those
changes look wrong.

"Problematic" is anchored on the registry's own rules wherever possible, since
those are objective: bio.tools caps description at 1000 characters and name at
100, and rejects the SPDX -only / -or-later licence forms outright (observed
directly in the gh2biotools failures). The remaining rules are judgement calls
and are labelled as such in the output.

Comparison is pre-conversion vs *today*, so it is the net effect. Where the
registry refused a push, a later import may have restored the old value, which
is why some fields show fewer changes than the conversion actually wrote.
"""

import argparse
import csv
import os
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

CONVERT = "convert bioconductor to biotools format"
ASSIGNED = ["credit", "description", "documentation", "download",
            "homepage", "license", "publication", "version"]
CONTROL = ["name", "topic", "function", "link", "toolType"]
PLACEHOLDER = re.compile(r"^10\.18129/B9\.bioc\.", re.I)
# The registry publishes its own enumeration; "-or-later" forms are in it, so
# a pattern match over-reports. Validate against the list itself.
try:
    from bc2bt.biotools_license import BIOTOOLS_LICENSES as ACCEPTED_LICENCES
except Exception:
    ACCEPTED_LICENCES = frozenset()
DESC_MAX, NAME_MAX = 1000, 100


def git(repo, *a, check=True):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True, check=check).stdout


def deep_sort(v):
    """Sort every nested array, the way the pipeline's own jq step does.

    The import action re-writes each file with
    jq 'walk(if type == "array" then sort else . end)', so files written after
    the conversion have sorted arrays while the pre-conversion ones may not.
    Comparing raw JSON therefore reports pure reordering as a data change; this
    removes that artefact.
    """
    if isinstance(v, list):
        return sorted((deep_sort(x) for x in v),
                      key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    if isinstance(v, dict):
        return {k: deep_sort(v[k]) for k in sorted(v)}
    return v


def norm(v):
    """Empty-ish values collapse to None; everything else to order-insensitive JSON."""
    if v in (None, "", [], {}):
        return None
    return json.dumps(deep_sort(v), sort_keys=True, ensure_ascii=False)


def urls(field_value):
    out = []
    for item in field_value or []:
        if isinstance(item, dict) and item.get("url"):
            out.append(item["url"])
    return out


def transition(b, a):
    nb, na = norm(b), norm(a)
    if nb is None and na is None:
        return "absent"
    if nb is None:
        return "added"
    if na is None:
        return "emptied"
    return "unchanged" if nb == na else "replaced"


def problems(field, b, a):
    """Return a list of (label, objective?) for a single field change."""
    out = []
    if field == "homepage":
        hb, ha = (b or ""), (a or "")
        if hb and ha and hb != ha:
            if "bioconductor.org" in ha and "bioconductor.org" not in hb:
                out.append(("project site replaced by the Bioconductor page", False))
    elif field == "license":
        if a and str(a) not in ACCEPTED_LICENCES:
            out.append(("outside the bio.tools licence vocabulary", True))
        # Bioconductor is authoritative for licence, so a change to a valid
        # identifier is the intended outcome, not a problem.
        if b and not a:
            out.append(("licence removed", False))
        if b and not a:
            out.append(("licence removed", False))
    elif field == "description":
        if a and len(a) > DESC_MAX:
            out.append((f"over the {DESC_MAX}-character limit", True))
        if b and a and b != a:
            out.append(("curated description replaced", False))
    elif field == "publication":
        bd = {(p.get("doi") or "").lower() for p in (b or []) if p.get("doi")}
        ad = {(p.get("doi") or "").lower() for p in (a or []) if p.get("doi")}
        b_real = {d for d in bd if not PLACEHOLDER.match(d)}
        a_real = {d for d in ad if not PLACEHOLDER.match(d)}
        lost = b_real - a_real
        if lost and not a_real:
            out.append(("real DOI displaced by the Bioconductor placeholder", False))
        elif lost:
            out.append(("real DOI lost", False))
        if bd and bd == ad:
            if any(p.get("metadata") for p in (b or [])) and \
               not any(p.get("metadata") for p in (a or [])):
                out.append(("publication metadata stripped", False))
    elif field == "credit":
        for c in (a or []):
            if len(c.get("name") or "") > NAME_MAX:
                out.append((f"credit name over the {NAME_MAX}-character limit", True))
                break
        # Before and after are usually both Bioconductor-derived author lists,
        # so "replaced" on its own says little. What actually goes missing is
        # contact detail and named people.
        eb = {(c.get("email") or "").lower() for c in (b or []) if c.get("email")}
        ea = {(c.get("email") or "").lower() for c in (a or []) if c.get("email")}
        if eb - ea:
            out.append(("contact email dropped", False))
        nb = {(c.get("name") or "").strip().lower() for c in (b or []) if c.get("name")}
        na = {(c.get("name") or "").strip().lower() for c in (a or []) if c.get("name")}
        if nb - na:
            out.append(("named person removed from credit", False))
    elif field in ("documentation", "download"):
        ub, ua = urls(b), urls(a)
        for u in ua:
            if ", " in u or not str(u).startswith(("http://", "https://")):
                out.append(("malformed URL", True))
                break
        # "bioconductor.org" alone misses the broken http://bioconductor/...
        # form that many old records carried, and replacing that with a working
        # URL is a repair rather than a loss.
        def is_bioc(u):
            return "bioconductor" in str(u).split("//")[-1].split("/")[0].lower()
        gone = [u for u in ub if u not in ua and not is_bioc(u)]
        repaired = [u for u in ub if u not in ua and is_bioc(u)
                    and "bioconductor.org" not in str(u)]
        if gone and ub and ua:
            out.append((f"third-party {field} URL dropped", False))
        if repaired:
            out.append((f"broken bioconductor {field} URL repaired", None))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--ref", default="origin/master")
    ap.add_argument("--out", default="fields")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    first_pre = {}
    for line in open(os.environ["FIRST_PRE"]):
        if "\t" in line:
            path, oid = line.rstrip("\n").split("\t")
            first_pre[path] = oid
    shas = ["(from first_pre.tsv)"]
    pre_keys = {p: o for p, o in first_pre.items() if o != "0" * 40}
    print(f"{len(shas)} conversion commits, "
          f"{len(pre_keys):,} pre-existing entries rewritten", flush=True)

    # before: exact replaced blobs, by object id
    keys = sorted(set(pre_keys.values()))
    proc = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"],
                          input=("\n".join(keys) + "\n").encode(),
                          capture_output=True, check=False)
    blobs, buf, pos = {}, proc.stdout, 0
    for k in keys:
        nl = buf.find(b"\n", pos)
        if nl < 0:
            break
        head = buf[pos:nl].decode("utf-8", "replace")
        if head.endswith((" missing", " ambiguous")):
            pos = nl + 1
            continue
        size = int(head.rsplit(" ", 1)[1])
        try:
            blobs[k] = json.loads(buf[nl + 1:nl + 1 + size].decode("utf-8", "replace"))
        except Exception:
            pass
        pos = nl + 1 + size + 1
    before = {p: blobs[o] for p, o in pre_keys.items() if o in blobs}

    # after: the tree the replay produced
    paths = sorted(pre_keys)
    after = {}
    for p in paths:
        f = repo / p
        if f.exists():
            try:
                after[p] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    print(f"read {len(before):,} before / {len(after):,} after", flush=True)

    trans = defaultdict(Counter)
    probs = defaultdict(Counter)
    good = defaultdict(Counter)
    prob_obj = defaultdict(Counter)
    rows = []
    n = 0
    for p in paths:
        b, a = before.get(p), after.get(p)
        if b is None or a is None:
            continue
        n += 1
        tool = p.split("/")[1]
        for field in ASSIGNED + CONTROL:
            t = transition(b.get(field), a.get(field))
            trans[field][t] += 1
            if field in ASSIGNED:
                for label, objective in problems(field, b.get(field), a.get(field)):
                    if objective is None:          # an improvement, tracked separately
                        good[field][label] += 1
                        continue
                    probs[field][label] += 1
                    prob_obj[field][objective] += 1
                    rows.append({"tool": tool, "field": field, "transition": t,
                                 "problem": label,
                                 "objective": objective,
                                 "before": json.dumps(b.get(field), ensure_ascii=False)[:200],
                                 "after": json.dumps(a.get(field), ensure_ascii=False)[:200]})
    with open(out / "field_problems.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["tool", "field", "transition", "problem",
                                           "objective", "before", "after"])
        w.writeheader(); w.writerows(rows)

    print(f"\ncompared {n:,} entries\n")
    hdr = f"{'field':<14}{'changed':>9}{'replaced':>10}{'added':>8}{'emptied':>9}{'unchanged':>11}{'problematic':>13}"
    print(hdr); print("-" * len(hdr))
    for field in ASSIGNED:
        c = trans[field]
        changed = c["replaced"] + c["added"] + c["emptied"]
        pr = sum(probs[field].values())
        print(f"{field:<14}{changed:>9,}{c['replaced']:>10,}{c['added']:>8,}"
              f"{c['emptied']:>9,}{c['unchanged']:>11,}{pr:>13,}")
    print("-" * len(hdr))
    for field in CONTROL:
        c = trans[field]
        changed = c["replaced"] + c["added"] + c["emptied"]
        print(f"{field:<14}{changed:>9,}{c['replaced']:>10,}{c['added']:>8,}"
              f"{c['emptied']:>9,}{c['unchanged']:>11,}{'-':>13}")
    print("\n(the block below the line is fields the updater does not assign)")

    print("\nimprovements picked up along the way")
    for field in ASSIGNED:
        for label, cnt in good[field].most_common():
            print(f"    [+] {field}: {label:<48} {cnt:>6,}")

    print("\nproblems in detail  [R] = rejected by the registry, [J] = judgement")
    for field in ASSIGNED:
        if not probs[field]:
            continue
        print(f"\n  {field}")
        for label, cnt in probs[field].most_common():
            objective = any(r["problem"] == label and r["objective"] for r in rows)
            print(f"    {'[R]' if objective else '[J]'} {label:<52} {cnt:>6,}")

    summary = {
        "entries_compared": n,
        "transitions": {f: dict(trans[f]) for f in ASSIGNED + CONTROL},
        "problems": {f: dict(probs[f]) for f in ASSIGNED if probs[f]},
    }
    (out / "field_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nwrote {out}/field_summary.json and field_problems.csv")


if __name__ == "__main__":
    main()
