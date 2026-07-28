# Unified `cogni` CLI

The application-facing CLI uses canonical SourceAsset and DocBundle
vocabulary:

```bash
cogni assets add paper.pdf --bundle phd/rag
cogni assets list --bundle phd/rag
cogni assets show src-...
cogni assets locate src-...
cogni assets delete src-... --yes --reason "superseded"
cogni assets deleted

cogni doc-bundles create phd/rag
cogni doc-bundles list
cogni doc-bundles locate bun-...
cogni doc-bundles delete bun-... --recursive --yes
cogni doc-bundles deleted
```

Blob cleanup is dry-run planning by default:

```bash
cogni cleanup blobs
cogni cleanup blobs --dry-run --older-than 7d
cogni cleanup blobs --older-than 7d --yes --batch-size 100
```

Physical deletion never occurs without `--yes`. A fresh plan is created and
Storage revalidates every candidate against current live references during
execution.

Context and Storage options belong on actionable leaf commands:

```bash
cogni assets add paper.pdf \
  --bundle phd/rag \
  --tenant-id acme \
  --project-id research \
  --scope environment=development \
  --storage-root /tmp/cognityx \
  --catalog-path /tmp/cognityx/catalog.sqlite3
```

Use `--storage-config` instead of `--storage-root` for configured profiles.
They are mutually exclusive. `cogni describe` remains catalog-lazy;
`cogni describe --assets` intentionally initializes and reports catalog
routing.

Successful stdout is JSON. Diagnostics go to stderr. Exit codes are `0` for
success, `1` for operational failure, `2` for arguments or missing
confirmation, `3` for inaccessible resources, and `4` for authorization
rejection.

## Shared Blob safety

```text
Asset A ─┐
Asset B ─┼──→ Blob
Asset C ─┘
```

Deleting Asset A creates an auditable tombstone. It does not remove the
shared Blob while B or C still references it.
