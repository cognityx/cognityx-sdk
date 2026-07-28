# Cognityx Python SDK

[![CI](https://github.com/cognityx/cognityx-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/cognityx/cognityx-sdk/actions/workflows/ci.yml)

The primary application-facing Python SDK for Cognityx.

```python
from datetime import timedelta
from cognityx import Cogni

cogni = Cogni.load()
created = cogni.assets.add("paper.pdf", bundle="phd/rag")
deleted = cogni.assets.delete(created.asset_id, reason="superseded")
plan = cogni.cleanup.plan_blobs(older_than=timedelta(days=7))
```

`cognityx` is a thin composition layer over the independently testable
`cognityx-resource`, `cognityx-storage`, and `cognityx-ingest` repositories. It
does not replace their domain models or persistence behavior.

The same lifecycle is available through the unified CLI:

```bash
cogni assets add paper.pdf --bundle phd/rag
cogni assets delete src-... --yes
cogni assets deleted
cogni cleanup blobs --dry-run
cogni cleanup blobs --older-than 7d --yes
```

Asset deletion is logical and auditable. Blob cleanup is a separate,
dry-run-first and reference-safe operation.

## Contributing

```bash
uv sync --extra dev
uv run pytest
uv run mkdocs build --strict
uv build
uv run python scripts/verify_wheel_install.py
```

GitHub CI runs these same commands, automatically collects every test below
`tests/`, and verifies the independently installable wheel.
