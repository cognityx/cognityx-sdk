# Cognityx Python SDK

The SDK provides one application-facing command, `cogni`, and one Python entry
point, `Cogni`. A user can give it a PDF and receive stable identifiers for the
original file, the work performed, and the structured document produced.

## Where It Fits

```text
local files or registered assets
              ↓
            cogni
              ↓
Resource context + Ingest + Storage + Jobs + optional Inference
              ↓
structured documents and page evidence
              ↓
           DataForge
```

`Cogni` does not replace the component services. It loads and connects their
existing APIs so applications do not need to assemble them manually.

## Start Here

```bash
cogni asset add report.pdf --bundle research/reports
cogni ingest report.pdf
cogni ingest --bundle research/reports
cogni job status <job-id>
cogni document show <document-id>
```

No storage path is required. The configured Storage Runtime chooses the
physical provider and logical roles.

The project records its preferred document readers once in
`.cognityx/ingest.toml`. After that, the normal command remains:

```bash
cogni ingest document.pdf
```

Ordinary users do not select a parser or model on each run. An operator may
enable Docling, PyMuPDF, or bounded Cognityx Inference resolution through the
configuration. Inference proposals never replace observed PDF facts.

- [Preferred CLI](cli.md)
- [Python API](api.md)
- [Architecture](architecture.md)
- [Concepts](concepts.md)

## Deletion In One Minute

Deleting an asset or bundle removes the logical record first. Deleting a run or
document removes only generated outputs. Raw bytes are physically removed only
after Storage proves that no live SourceAsset references them.

## Future Roadmap

Planned work includes reference-only external URI ingestion, true distributed
workers for large jobs, and an always-running Storage cleanup service. The
future cleanup service will automate the current reference-safe process rather
than bypass it.
