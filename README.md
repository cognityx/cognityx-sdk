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
```

```bash
cogni asset add paper.pdf --bundle research
cogni ingest paper.pdf
cogni ingest --asset src-...
cogni ingest --bundle research
cogni job status <job-id>
cogni document show <document-id>
```

The SDK is a thin composition layer. Ingest still owns document processing,
Storage owns bytes and safe cleanup, Resource owns execution context, and Jobs
owns durable status and ordered events.

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
