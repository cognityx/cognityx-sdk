# Cognityx Python SDK

[![CI](https://github.com/cognityx/cognityx-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/cognityx/cognityx-sdk/actions/workflows/ci.yml)

`cogni` is the primary command for working with Cognityx. It lets a user
organize original files, turn PDFs into structured documents, monitor the work,
and inspect the result without choosing physical storage paths.

```text
user or application
        ↓
       cogni
        ↓
Resource · Ingest · Storage · Jobs · optional Inference
        ↓
     DataForge
        ↓
Training · Inference · Evaluator · Experiments
```

```bash
cogni asset add paper.pdf --bundle research
cogni ingest paper.pdf
cogni ingest --asset src-...
cogni ingest --bundle research
cogni job status <job-id>
cogni document show <document-id>
cogni artifact read <document-id> source-graph
cogni provenance resolve <document-id> <address-id>
cogni storage locate storage://local-main/artifacts/example/report.json
```

The `cogni experiment` group validates and runs frozen research plans and
assembles accumulated evidence. Cognityx Experiments still owns the compiler,
scheduler, findings, and publication rules; the SDK only delegates.

Projects choose their document readers once in `.cognityx/ingest.toml`; users
do not repeat parser options on every command:

```toml
[ingest]
parser_policy = "compare"
parser_backends = ["pymupdf", "docling", "basic"]

[ingest.inference]
enabled = false
```

Install the optional rich readers with `pip install "cognityx[rich-ingest]"`.
Without a configuration file or that extra, Ingest safely uses its Basic PDF
reader.

The SDK is a thin composition layer. Ingest still owns document processing,
Storage owns bytes and safe cleanup, Resource owns execution context, and Jobs
owns durable status and ordered events.

After ingestion, `cogni artifact` can read the structured content, the map back
to the original source, and the stable evidence addresses. The source map is
technically called a Source Graph. A provenance address is a durable identifier
for one exact part of that graph. These reads use logical `storage://` addresses;
users do not provide or receive a physical filesystem path.

The current parser policies (`fixed`, `rule`, `fallback`, `compare`, and
`agent`) are the controls that reach parser execution today. Ingest also has
adaptive planning terms (`deterministic`, `hybrid`, and `llm-directed`), but the
merged application path does not yet connect every adaptive plan to a concrete
provider and parser invocation. The SDK reports the comparable planning term in
`cogni ingest-config show` but does not offer a routing flag that would be
accepted and ignored.

Optional rich parsing and ambiguity resolution use the approved
`cognityx-inference` client. A model may propose a relationship, but Ingest
accepts it only after deterministic source-anchor validation.

See the [documentation](docs/index.md) for the complete flow, deletion rules,
compatibility notes, and future roadmap.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run mkdocs build --strict
uv build
uv run python scripts/verify_wheel_install.py
```
