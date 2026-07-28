# Cognityx Python SDK

The SDK provides the application-facing `Cogni` facade while preserving the
independent component boundaries underneath it.

```python
from cognityx import Cogni

cogni = Cogni.load()
result = cogni.assets.add("paper.pdf", bundle="phd/rag")
asset = cogni.assets.get(result.asset_id)
```

The SDK currently exposes SourceAsset and DocBundle operations. The unified
`cogni` command-line interface is intentionally deferred to Job 4B.
