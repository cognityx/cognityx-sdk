# API

## Loading

```python
from cognityx import Cogni

cogni = Cogni.load()
```

Advanced callers may provide `context`, `context_file`, `context_overrides`,
`cwd`, `user_context_file`, `storage_runtime`, `storage_config`,
`catalog_path`, and an Ingest `control` client. Conflicting context or Storage
arguments are rejected.

## Assets

```python
result = cogni.assets.add("interview.mp3", bundle="research/interviews")
asset = cogni.assets.get(result.asset_id)
items = cogni.assets.list(bundle="research/interviews")

with cogni.assets.open(asset.asset_id) as stream:
    content = stream.read()

location = cogni.assets.locate(asset.asset_id)
deleted = cogni.assets.delete(asset.asset_id, reason="superseded")
deleted_assets = cogni.assets.list_deleted()
```

## DocBundles

```python
bundle = cogni.doc_bundles.create("research/interviews")
bundles = cogni.doc_bundles.list()
location = cogni.doc_bundles.locate(bundle.bundle_id)
deleted = cogni.doc_bundles.delete(
    bundle.bundle_id,
    recursive=True,
    reason="project closed",
)
deleted_bundles = cogni.doc_bundles.list_deleted()
```

## Blob cleanup

```python
from datetime import timedelta

plan = cogni.cleanup.plan_blobs(older_than=timedelta(days=7))

# Planning never deletes physical objects.
result = cogni.cleanup.execute_blobs(plan, batch_size=100)
```

All returned objects are canonical models from the underlying component
repositories.
