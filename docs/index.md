# Cognityx Python SDK

The SDK provides the application-facing `Cogni` facade while preserving the
independent component boundaries underneath it.

```python
from datetime import timedelta
from cognityx import Cogni

cogni = Cogni.load()
created = cogni.assets.add("paper.pdf", bundle="phd/rag")
deleted = cogni.assets.delete(created.asset_id, reason="superseded")
plan = cogni.cleanup.plan_blobs(older_than=timedelta(days=7))
```

The SDK exposes SourceAsset and DocBundle lifecycle operations plus
dry-run-first Blob cleanup. The `cogni` CLI delegates through this same
Python facade.
