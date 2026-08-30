"""Generate a contents report on the Research Software Ecosystem metadata commons.

For every tool folder under ``<content>/data``, work out which upstream sources
have deposited a native metadata record, and summarise the result as:

    report/global_upset.png     UpSet plot of source co-occurrence
    report/summary.md           human-readable intersection table
    report/summary.json         machine-readable counts, for downstream reuse
    report/counts.csv           per-source totals
    report/detailed_counts.md   per-tool matrix (only with --detailed)

Sources are detected by matching file *patterns* against the names present in a
tool folder, rather than by building a filename from the bio.tools id. Upstream
package names frequently differ from the tool id -- data/impute holds
``bioconda_bioconductor-impute.yaml`` and ``r-bioc-impute.debian.yaml`` -- and an
id-based template scores every such record as absent.
"""

import argparse
import csv
import fnmatch
import json
import os
import sys

# Native upstream records: sources that deposit their own metadata in a tool
# folder. Detected by file name pattern, because the upstream package name is
# not always the bio.tools id.
NATIVE_SOURCES = (
    ("bio.tools", ("*.biotools.json",)),
    ("OEB Metrics", ("*.oeb.metrics.json",)),
    ("BioContainers", ("*.biocontainers.yaml", "biocontainers.yaml")),
    ("Bioconductor", ("*.bioconductor.json",)),
    ("Bioconda", ("bioconda_*.yaml", "*.bioconda.yaml")),
    ("BIII", ("*.neubias.raw.json", "*.biii.json")),
    ("Galaxy", ("*.galaxy.json",)),
    ("Debian Med", ("*.debian.yaml",)),
    ("WorkflowHub", ("*.workflowhub.json",)),
)

# Representations the RSEc generates *from* the sources above. A
# .bioschemas.jsonld file is a 1:1 conversion of the bio.tools record, so
# counting it as a source double-counts bio.tools and inflates every
# intersection it appears in. Included only with --include-derived.
DERIVED_SOURCES = (("Bioschemas", ("*.bioschemas.jsonld",)),)

# Files that are not metadata records: pre-edit copies kept by the importers.
IGNORED_SUFFIXES = (".backup",)


def tool_folders(data_path):
    """Yield (tool_id, [file names]) for every tool folder under data_path."""
    with os.scandir(data_path) as entries:
        folders = sorted(
            (entry for entry in entries if entry.is_dir()), key=lambda e: e.name
        )
    for folder in folders:
        with os.scandir(folder.path) as entries:
            files = [
                entry.name
                for entry in entries
                if entry.is_file() and not entry.name.endswith(IGNORED_SUFFIXES)
            ]
        yield folder.name, files


def sources_present(files, sources):
    """Return one boolean per source, True when the folder holds its record."""
    return [
        any(fnmatch.fnmatch(name, pattern) for pattern in patterns for name in files)
        for _, patterns in sources
    ]


def describe(combination, source_names):
    """Render a source combination as e.g. 'bio.tools + Bioconda'."""
    present = [name for name, flag in zip(source_names, combination) if flag]
    if not present:
        return "(no source)"
    if len(present) == 1:
        return f"{present[0]} only"
    return " + ".join(present)


def build_table(data_path, sources):
    import pandas as pd

    source_names = [name for name, _ in sources]
    rows = {}
    for tool_id, files in tool_folders(data_path):
        rows[tool_id] = sources_present(files, sources)
    if not rows:
        sys.exit(f"no tool folders found under {data_path}")
    return pd.DataFrame.from_dict(rows, orient="index", columns=source_names)


def write_summary_md(path, df, counts):
    """Intersection table, labelled by source name rather than by True/False."""
    source_names = list(df.columns)
    total = len(df)
    lines = [
        "# RSEc contents summary",
        "",
        f"{total} tool folders, {len(source_names)} sources.",
        "",
        "## Tools per source",
        "",
        "| source | tools | share |",
        "| --- | --- | --- |",
    ]
    for name in source_names:
        hits = int(df[name].sum())
        lines.append(f"| {name} | {hits} | {100.0 * hits / total:.1f}% |")
    lines += [
        "",
        "## Tools per number of sources",
        "",
        "| sources | tools | share |",
        "| --- | --- | --- |",
    ]
    degrees = df.sum(axis=1).value_counts().sort_index()
    for degree, tools in degrees.items():
        lines.append(f"| {int(degree)} | {int(tools)} | {100.0 * tools / total:.1f}% |")
    lines += [
        "",
        "## Source combinations",
        "",
        "| sources present | tools |",
        "| --- | --- |",
    ]
    for combination, tools in counts.sort_values(ascending=False).items():
        lines.append(f"| {describe(combination, source_names)} | {int(tools)} |")
    with open(path, "w") as summary_file:
        summary_file.write("\n".join(lines) + "\n")


def write_summary_json(path, df, counts):
    """Machine-readable counts, so the numbers can be reused without parsing markdown.

    Deliberately carries no generation timestamp: the report is committed by CI
    only when it differs from the previous run, and a timestamp would force a
    commit on every run even when nothing changed.
    """
    source_names = list(df.columns)
    total = len(df)
    patterns = dict(NATIVE_SOURCES + DERIVED_SOURCES)
    report = {
        "tools_total": total,
        "sources": {
            name: {
                "tools": int(df[name].sum()),
                "share": round(float(df[name].sum()) / total, 4),
                "patterns": list(patterns[name]),
            }
            for name in source_names
        },
        "sources_per_tool": {
            str(int(degree)): int(tools)
            for degree, tools in df.sum(axis=1).value_counts().sort_index().items()
        },
        "combinations": [
            {
                "sources": [
                    name for name, flag in zip(source_names, combination) if flag
                ],
                "tools": int(tools),
            }
            for combination, tools in counts.sort_values(ascending=False).items()
        ],
    }
    with open(path, "w") as json_file:
        json.dump(report, json_file, indent=2, sort_keys=True)
        json_file.write("\n")


def write_counts_csv(path, df):
    total = len(df)
    with open(path, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["source", "tools", "share"])
        for name in df.columns:
            hits = int(df[name].sum())
            writer.writerow([name, hits, f"{float(hits) / total:.4f}"])


def write_detailed_md(path, df):
    with open(path, "w") as md_file:
        df.replace({True: "✓", False: "🗙"}).to_markdown(buf=md_file, tablefmt="github")


def write_upset_png(path, counts, min_subset_size):
    """Draw the UpSet plot. Returns (subsets_drawn, subsets_omitted, tools_omitted)."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot
    from upsetplot import plot as upset_plot

    drawn = counts[counts >= min_subset_size]
    omitted = counts[counts < min_subset_size]
    if drawn.empty:
        sys.exit(f"no source combination reaches --min-subset-size={min_subset_size}")
    figure = pyplot.figure(figsize=(16, 8))
    upset_plot(drawn, fig=figure, show_counts=True, sort_by="cardinality")
    pyplot.savefig(path, dpi=150, bbox_inches="tight")
    pyplot.close(figure)
    return len(drawn), len(omitted), int(omitted.sum())


def main():
    parser = argparse.ArgumentParser(
        description="Generate a contents report on the Research Software Ecosystem"
    )
    parser.add_argument("path", help="path to a checkout of the content repository")
    parser.add_argument(
        "--include-derived",
        action="store_true",
        help="also count RSEc-generated representations (Bioschemas) as sources",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="also write report/detailed_counts.md, a per-tool matrix (large)",
    )
    parser.add_argument(
        "--min-subset-size",
        type=int,
        default=1,
        help="omit source combinations below this size from the plot, for a tidier "
        "figure (default: 1, plot everything). Note that upsetplot derives the "
        "per-source totals shown on the left from the plotted combinations only, "
        "so any value above 1 understates them; summary.md, summary.json and "
        "counts.csv always carry the true totals",
    )
    args = parser.parse_args()

    data_path = os.path.join(args.path, "data")
    if not os.path.isdir(data_path):
        sys.exit(f"no data/ folder in {args.path}")
    report_path = os.path.join(args.path, "report")
    os.makedirs(report_path, exist_ok=True)

    sources = NATIVE_SOURCES + (DERIVED_SOURCES if args.include_derived else ())
    df = build_table(data_path, sources)
    counts = df.groupby(list(df.columns)).size()
    print(f"{len(df)} tool folders, {len(df.columns)} sources")
    for name in df.columns:
        print(f"  {name:<15} {int(df[name].sum()):6d}")

    write_summary_md(os.path.join(report_path, "summary.md"), df, counts)
    write_summary_json(os.path.join(report_path, "summary.json"), df, counts)
    write_counts_csv(os.path.join(report_path, "counts.csv"), df)
    if args.detailed:
        write_detailed_md(os.path.join(report_path, "detailed_counts.md"), df)

    drawn, omitted, tools_omitted = write_upset_png(
        os.path.join(report_path, "global_upset.png"), counts, args.min_subset_size
    )
    print(f"plotted {drawn} of {drawn + omitted} source combinations")
    if omitted:
        print(
            f"omitted {omitted} combinations below "
            f"--min-subset-size={args.min_subset_size}, covering {tools_omitted} "
            "tools; the per-source totals in the figure are for plotted "
            "combinations only"
        )


if __name__ == "__main__":
    main()
