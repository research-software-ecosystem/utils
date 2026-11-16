# Design proposal: syntactic validators for imported files

Status: **proposal — not implemented**. This document describes the design for
per-source validation scripts; implementation starts once the open questions at
the end are settled.

## 1. Goal and scope

Each import action in this repository writes files into
`research-software-ecosystem/content`. Nothing currently checks that those
files are well-formed beyond the Debian YAML parse check in
`scripts/files-validator/debian_validator.py`. The goal is one validator per
source that checks, for every imported file:

1. **Format**: the file parses (JSON/YAML) and has the structure this source
   is expected to produce (required fields, right types, no unexpected
   top-level shape).
2. **Values**: every field whose values obey a known syntax actually complies
   with it — ORCIDs, DOIs, URLs, emails, PMIDs/PMCIDs, EDAM URIs, CURIEs,
   version strings, dates, MD5 sums, etc.

Checks are **syntactic and offline**: no network calls (no DOI resolution, no
URL liveness). An optional online mode can be added later (see Q5).

### Sources and the files they produce

| Source       | Files validated                                             | Format |
|--------------|-------------------------------------------------------------|--------|
| biotools     | `data/<id>/<id>.biotools.json`                              | JSON   |
| bioconda     | `imports/bioconda/bioconda_<name>.yaml`, `data/<id>/bioconda_<id>.yaml` | YAML |
| bioconductor | `data/<id>/<id>.bioconductor.json`, `imports/bioconductor/` | JSON   |
| biocontainers| `data/<id>/<id>.biocontainers.yaml`                         | YAML   |
| debian-med   | `data/<id>/<id>.debian.yaml`, `imports/debian-med/`         | YAML   |
| galaxy       | `data/<id>/<id>.galaxy.json`, `imports/galaxy/`             | JSON   |
| workflowhub  | `imports/workflowhub/<n>.workflowhub.json`, `data/<id>/<id>.workflowhub.json` | JSON |
| openebench   | `data/<id>/<id>.oeb.metrics.json`                           | JSON   |
| biii         | `data/<id>/<id>.neubias.raw.json`                           | JSON   |

Derived artifacts (`*.jsonld`, `*.ttl`, `*.bioschemas.jsonld`) are produced by
`bioschemas-gen` from the files above and are **out of scope** for these
validators (they would deserve an RDF-level check of their own).

## 2. Layout

```
validation/
├── DESIGN.md                      (this document)
├── requirements.txt               pyyaml, jsonschema
├── common_checks.py               shared value validators + runner plumbing
├── schemas/
│   ├── biotools.schema.json
│   ├── bioconda.schema.json
│   ├── bioconductor.schema.json
│   ├── biocontainers.schema.json
│   ├── debian-med.schema.json
│   ├── galaxy.schema.json
│   ├── workflowhub.schema.json
│   ├── openebench.schema.json
│   └── biii.schema.json
├── validate_biotools.py           one thin CLI per source
├── validate_bioconda.py
├── validate_bioconductor.py
├── validate_biocontainers.py
├── validate_debian_med.py
├── validate_galaxy.py
├── validate_workflowhub.py
├── validate_openebench.py
├── validate_biii.py
└── tests/
    ├── fixtures/<source>/valid/…      real sampled files, committed
    ├── fixtures/<source>/invalid/…    hand-broken variants, one defect each
    └── test_<source>.py               offline unittest, like the other suites
```

One script per source keeps each source's rules reviewable by the person who
knows that source, and lets CI run them independently; `common_checks.py`
keeps every cross-cutting rule (what *is* a valid ORCID) in exactly one place.

*Alternative considered*: putting each script inside its import action
directory (`debian-med-import/validate.py`, …). Rejected as the default
because three sources (biotools, biocontainers, openebench) have import jobs
defined elsewhere, so there is no directory for them here, and because the
schemas and shared checks would end up far from the scripts using them. See
open question Q1.

## 3. How a validator works

Structure and values are checked in one pass using **JSON Schema (draft
2020-12) plus custom format checkers**, via the `jsonschema` library:

- Each source gets a schema file describing its structure: required fields,
  types, and `"format"` annotations on value-constrained fields
  (`"format": "orcid"`, `"format": "doi"`, …). YAML sources are loaded with
  `yaml.safe_load` and validated against the same kind of schema.
- `common_checks.py` registers the custom formats with a
  `jsonschema.FormatChecker`, so a wrong ORCID is reported by the same
  machinery, with the same JSON-path, as a missing required field.
- Schemas are *descriptive of what the importer writes*, not aspirational:
  they start from the current output (sampled from `content`) so that a clean
  run on today's data is green, and tighten over time.

Why JSON Schema instead of hand-rolled per-field code: the structure rules
become data that can be read, diffed and reviewed without reading Python; the
error reporting (path, message) comes for free; and other tooling can reuse
the schema files. The hand-rolled alternative is Q2.

### Shared value checkers (`common_checks.py`)

| Format name     | Rule (all offline)                                                       |
|-----------------|--------------------------------------------------------------------------|
| `orcid`         | `\d{4}-\d{4}-\d{4}-\d{3}[0-9X]` **and** ISO 7064 mod 11-2 checksum; also accepts the `https://orcid.org/` URL form |
| `doi`           | `10\.\d{4,9}/\S+`, no whitespace, no `<`/`>`; tolerates a `doi:`/`https://doi.org/` prefix |
| `url`           | `urllib.parse`: scheme in {http, https, ftp}, non-empty host, no spaces   |
| `email`         | one `@`, valid dot-atom local part, domain with at least one dot, no spaces |
| `pmid`          | 1–8 digits, no leading zero                                               |
| `pmcid`         | `PMC\d+`                                                                  |
| `edam-uri`      | `http://edamontology.org/(topic|operation|data|format)_\d{4}`             |
| `biotools-id`   | bio.tools ID grammar: `[A-Za-z0-9_.-]+` (what bio.tools accepts on write) |
| `biotools-curie`| `biotools:<biotools-id>`                                                  |
| `curie`         | generic `<prefix>:<value>` with a known-prefix table (`doi`, `biotools`, `PMID`, `usegalaxy-eu`, `conda:bioconda`, …) for e.g. biocontainers `identifiers` |
| `iso-date`      | `YYYY-MM-DD` (plus `iso-datetime` for RFC 3339 timestamps)                |
| `md5`           | 32 lowercase hex chars                                                    |
| `scicrunch-id`  | `SCR_\d+`                                                                 |
| `debian-version`| Debian version policy grammar (epoch, upstream, revision)                 |
| `semverish`     | lenient `\d+(\.\d+)*([a-zA-Z0-9.+-]*)` for software versions              |
| `spdx-license`  | *warning-level only*: value in the SPDX list, vendored as a static table  |

Each checker is a small pure function with its own unit tests, usable outside
JSON Schema too (e.g. the bot in `scripts/biotools-pullrequest-bot` could
import it).

### Where the formats attach per source (from sampled real files)

- **biotools**: `credit[].orcidid` (orcid), `credit[].email`,
  `credit[].url`, `publication[].doi/pmid/pmcid`, `homepage`, `link[].url`,
  `download[].url`, `documentation[].url`, EDAM uris in
  `topic[].uri`/`function[].operation[].uri`/`…data.uri`/`…format.uri`,
  `biotoolsID`/`biotoolsCURIE`, `additionDate`/`lastUpdate` (iso-datetime).
- **bioconda**: `about.home/dev_url/doc_url` (url), `extra.identifiers[]`
  (curie), `package.name`, `package.version` (semverish).
- **bioconductor**: `Maintainer` (name + email), `URL` (comma-separated urls),
  `MD5sum` (md5), `Version`, `Date/Publication` (iso-date),
  `git_url` (url), `git_last_commit_date`.
- **biocontainers**: `home_url` (url), `identifiers[]` (curie: `biotools:`,
  `doi:`, `PMID:`, `usegalaxy-eu:`), `license` (spdx, warning),
  `total_pulls` (non-negative int).
- **debian-med**: `homepage` (url), `bib[].value` where `key == doi` (doi),
  `description_md5` (md5), `version` (debian-version), `registries[]`
  (per-registry entry syntax: bio.tools id, `SCR_…`, `OMICS_…`, conda name).
- **galaxy**: `Suite_source`/`Homepage` (url), `bio.tool_ID` (biotools-id),
  `Related_Workflows[].link` (url), EDAM label lists (non-empty strings;
  URIs once galaxy_codex#709 lands).
- **workflowhub**: `doi` (doi), `link`/`source` (url), `create_time`/
  `update_time` (iso-date), `id` (int), `license` (spdx, warning).
- **openebench**: `@id` (url with `openebench.bsc.es` path shape),
  `@license` (url), booleans in `project.*`.
- **biii**: node URL fields (url), DOIs in publication fields.

## 4. CLI contract (identical for every script)

```
python validation/validate_<source>.py <content-checkout-path>
    [--glob PATTERN …]        override the default file set
    [--output text|github|json]   default text; github = ::error annotations
    [--warnings-as-errors]
    [--max-errors N]          stop after N (default: no limit)
```

- Exit `0`: all files valid (warnings allowed unless `--warnings-as-errors`).
- Exit `1`: at least one error. Exit `2`: usage/environment problem.
- Report format, one line per finding:
  `ERROR data/bwa/bwa.debian.yaml: bib[0].value: 'IO.1093/x' is not a valid DOI`
- Severity: **error** = malformed file, missing/mistyped required field,
  value failing a hard syntax (orcid, doi, url, email, pmid, pmcid, md5,
  edam-uri, curie). **Warning** = soft rules (unknown license identifier,
  unknown registry name, deprecated field present).
- A summary line at the end (`N files checked, E errors in F files, W warnings`)
  mirroring the existing `debian_validator.py` behaviour.

## 5. CI integration (follow-up, not part of the first PR)

The scripts are plain CLIs so they can run anywhere, but the intended use is
in the `content` repo's import workflow: after each `import <source>` job,
run the matching validator on the files that job just wrote, before the
commit/merge steps — so a malformed import fails its own feature branch
instead of landing on master. A small composite action
(`validation/action.yml`, taking `source` + `path` inputs) would mirror how
the import actions are consumed. First PR ships scripts + tests only.

## 6. Testing

Same conventions as the existing suites (`python3 -m unittest`, fully
offline): per source, a handful of real files committed as valid fixtures and
hand-broken copies (one defect each: truncated JSON, bad ORCID checksum, DOI
with a space, email without `@`, PMCID without prefix…) asserting both the
verdict and that the finding points at the right path. Plus unit tests per
format checker, including edge cases (ORCID ending in X, DOI with unusual
suffix characters, IDN URLs).

The lint workflow already covers style; validators and tests will be
ruff-clean from the start.

## 7. Open questions before implementation

- **Q1 — Placement**: central `validation/` directory (proposed) or one
  script inside each `<source>-import/` directory? (Three sources have no
  import directory in this repo, so central is cleaner. The request said "all
  located in different repositories" — if that meant each validator should
  live in a *different repo* (e.g. next to each upstream importer), say so;
  this proposal assumes one branch of `utils` holds them all.)
- **Q2 — Mechanism**: JSON Schema + custom formats (proposed), or pure-Python
  per-field checks with no schema dependency? Pure Python is simpler to debug
  but re-invents structure error reporting and makes the expected shape
  implicit.
- **Q3 — Strictness of unknown fields**: should schemas set
  `additionalProperties: false` (catches importer regressions early, but
  breaks loudly whenever an upstream adds a field) or tolerate unknown fields
  (proposed: tolerate, and revisit per source)?
- **Q4 — biii and openebench**: their raw formats are the least documented;
  OK to start their schemas minimal (parse + the handful of URL/DOI fields)
  and tighten later?
- **Q5 — Online checks**: a later `--online` flag could resolve DOIs, HEAD
  URLs and look up ORCIDs. Out of scope for v1 — confirm.
- **Q6 — EDAM term existence**: checking that an EDAM URI *exists in the
  ontology* (not just matches the pattern) is possible offline by vendoring
  the EDAM term list; include in v1 or keep pattern-only (proposed:
  pattern-only v1)?
