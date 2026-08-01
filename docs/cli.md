# Unified `cogni` CLI

## Organize Original Files

A SourceAsset is a recorded original file. A DocBundle is a named collection,
similar to a folder.

```bash
cogni bundle create research/reports
cogni bundle list
cogni bundle locate bun-...

cogni asset add report.pdf --bundle research/reports
cogni asset add ./incoming --bundle research --structure preserve
cogni asset list --bundle research/reports
cogni asset show src-...
cogni asset locate src-...
```

## Ingest PDFs

The same command accepts a path, an existing asset ID, or a complete bundle ID:

```bash
cogni ingest report.pdf
cogni ingest ./reports
cogni ingest --asset src-...
cogni ingest --bundle research/reports
```

The response includes the run ID, job ID, document IDs, asset IDs, page counts,
and stable artifact addresses. DataForge users do not need to select internal
metadata files.

## Monitor Work

```bash
cogni job list
cogni job status <job-id>
cogni job events <job-id>
cogni job watch <job-id>
cogni job cancel <job-id>
```

`events` replays ordered progress. `watch` reconnects at an event sequence and
continues until the job ends. Cancellation is checked between PDFs; the current
PDF parse remains synchronous.

## Inspect Generated Results

```bash
cogni run list
cogni run show <run-id>
cogni document list
cogni document show <document-id>
cogni artifact read <document-id> evidence
cogni artifact read <document-id> provenance
```

## Delete Safely

```bash
# Logical deletion; raw bytes are retained while referenced.
cogni asset delete src-... --yes --reason "superseded"
cogni bundle delete bun-... --recursive --yes

# Generated output deletion; SourceAsset bytes and job history remain.
cogni run delete <run-id> --yes
cogni document delete <document-id> --yes

# Storage-owned physical cleanup. Planning is the default.
cogni cleanup blobs --older-than 7d
cogni cleanup blobs --older-than 7d --yes
```

Storage rechecks every candidate before physical deletion. A future
always-running Storage service will execute this same safe cleanup process
automatically according to retention policy.

## Context And Advanced Storage Configuration

Normal commands load the configured Storage Runtime automatically:

```bash
cogni ingest report.pdf --tenant-id acme --project-id research
```

An operator may select a configuration explicitly:

```bash
cogni ingest report.pdf --storage-config .cognityx/storage.toml
```

Rich extraction and bounded inference are advanced operator controls:

```bash
cogni ingest report.pdf \
  --parser-policy fallback \
  --parser-backend docling \
  --parser-backend pymupdf \
  --parser-backend basic \
  --inference-config .cognityx/ingest-inference.toml
```

The Inference file contains an operator-approved target list. For local work,
its named server profile starts the worker and loads the configured model.
Only unresolved provenance tasks are sent, calls and tokens are bounded, and
invented anchors are rejected. DataForge users do not need these options.

Successful stdout is JSON. Diagnostics go to stderr. Exit codes are `0` for
success, `1` for operational failure, `2` for arguments or missing
confirmation, `3` for inaccessible resources, and `4` for authorization
rejection.

## Deprecated / Compatibility

The component-level `cognityx-ingest` command; plural `assets`, `doc-bundles`,
`jobs`, `runs`, `documents`, and `artifacts`; historical `sources` and
`bundles`; `jobs show`; ID-only `--bundle-id`; and `--storage-root` remain
temporarily available. New scripts use singular resource commands, bundle
paths, and normal Storage Runtime loading.

The old generated `source.pdf` artifact is not available. Use `cogni asset
show` or `cogni asset locate` for the original SourceAsset.
