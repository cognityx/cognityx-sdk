# Cognityx Python SDK

The primary application-facing Python SDK for Cognityx.

```python
from cognityx import Cogni

cogni = Cogni.load()
result = cogni.assets.add("paper.pdf", bundle="phd/rag")
asset = cogni.assets.get(result.asset_id)
```

`cognityx` is a thin composition layer over the independently testable
`cognityx-resource`, `cognityx-storage`, and `cognityx-ingest` repositories. It
does not replace their domain models or persistence behavior.

The unified `cogni` CLI is planned separately.
