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
Resource · Ingest · Storage · Jobs
        ↓
     DataForge
```

```bash
cogni assets add paper.pdf --bundle research
cogni ingest paper.pdf
cogni ingest --asset src-...
cogni ingest --bundle-id bun-...
cogni jobs status <job-id>
cogni documents show <document-id>
```

The SDK is a thin composition layer. Ingest still owns document processing,
Storage owns bytes and safe cleanup, Resource owns execution context, and Jobs
owns durable status and ordered events.

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
