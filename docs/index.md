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
settled content, source links, and evidence addresses
              ↓
           DataForge
              ↓
Training + Inference + Evaluator
              ↓
Experiments plans, evidence, and research material
```

`Cogni` does not replace the component services. It loads and connects their
existing APIs so applications do not need to assemble them manually.

The `cogni experiment` command is a thin door into Cognityx Experiments. It
validates frozen research plans, checks production readiness, shows or runs
their declared steps, reports durable status, and assembles existing research
material. The SDK does not copy the experiment compiler, scheduler, evidence
rules, or publication logic.

For a production research environment, install the `research-execution` extra.
It requests each owning component's execution dependencies, including
Training's complete LoRA/QLoRA stack. Add `research-tracking` when the frozen
profile selects MLflow. The preflight then checks Training runtime capability
and its separate configuration/data dry run before preregistration. Neither
probe loads a model or creates scientific evidence.

## Start Here

```bash
cogni asset add report.pdf --bundle research/reports
cogni ingest report.pdf
cogni ingest --bundle research/reports
cogni job status <job-id>
cogni document show <document-id>
cogni artifact read <document-id> canonical-content
cogni provenance resolve <document-id> <address-id>
cogni experiment validate research.yaml
cogni experiment plan research.yaml
cogni experiment preflight research.yaml --results-repo ./experiment-results
cogni experiment status <execution-id>
```

No storage path is required. The configured Storage Runtime chooses the
physical provider and logical roles.

Canonical content is the parser-neutral document form used by later Cognityx
steps. The Source Graph is a compact map from that content back to its source
structure. A provenance address is a stable identifier for an exact target in
that map. Together they let DataForge and audit tools check support without
reopening the original PDF or parser-specific bytes.

The project records its preferred document readers once in
`.cognityx/ingest.toml`. After that, the normal command remains:

```bash
cogni ingest document.pdf
```

Ordinary users do not select a parser or model on each run. An operator may
enable Docling, PyMuPDF, or bounded Cognityx Inference resolution through the
configuration. Inference proposals never replace observed PDF facts.

`cogni` is the primary user surface. The component-level `cognityx-ingest`
command remains only for compatibility with older scripts.

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
