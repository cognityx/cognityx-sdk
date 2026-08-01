# Unified `cogni` CLI

## Organize Original Files

A SourceAsset is a recorded original file. A DocBundle is a named collection,
similar to a folder.

```bash
cogni doc-bundles create research/reports
cogni doc-bundles list
cogni doc-bundles locate bun-...

cogni assets add report.pdf --bundle research/reports
cogni assets add ./incoming --bundle research --structure preserve
cogni assets list --bundle research/reports
cogni assets show src-...
cogni assets locate src-...
```

## Ingest PDFs

The same command accepts a path, an existing asset ID, or a complete bundle ID:

```bash
cogni ingest report.pdf
cogni ingest ./reports
cogni ingest --asset src-...
cogni ingest --bundle-id bun-...
```

The response includes the run ID, job ID, document IDs, asset IDs, page counts,
and stable artifact addresses. DataForge users do not need to select internal
metadata files.

## Monitor Work

```bash
cogni jobs list
cogni jobs status <job-id>
cogni jobs events <job-id>
cogni jobs watch <job-id>
cogni jobs cancel <job-id>
```

`events` replays ordered progress. `watch` reconnects at an event sequence and
continues until the job ends. Cancellation is checked between PDFs; the current
PDF parse remains synchronous.

## Inspect Generated Results

```bash
cogni runs list
cogni runs show <run-id>
cogni documents list
cogni documents show <document-id>
cogni artifacts read <document-id> evidence
```

## Delete Safely

```bash
# Logical deletion; raw bytes are retained while referenced.
cogni assets delete src-... --yes --reason "superseded"
cogni doc-bundles delete bun-... --recursive --yes

# Generated output deletion; SourceAsset bytes and job history remain.
cogni runs delete <run-id> --yes
cogni documents delete <document-id> --yes

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

Successful stdout is JSON. Diagnostics go to stderr. Exit codes are `0` for
success, `1` for operational failure, `2` for arguments or missing
confirmation, `3` for inaccessible resources, and `4` for authorization
rejection.

## Deprecated / Compatibility

The component-level `cognityx-ingest` command, `sources` and `bundles` aliases,
`jobs show`, `--bundle` for bundle ingestion, and `--storage-root` remain
temporarily available. New scripts should use `cogni`, `assets`,
`doc-bundles`, `jobs status`, `--bundle-id`, and normal Storage Runtime loading.

The old generated `source.pdf` artifact is not available. Use `cogni assets
show` or `cogni assets locate` for the original SourceAsset.
