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
```

## DocBundles

```python
bundle = cogni.doc_bundles.create("research/interviews")
bundles = cogni.doc_bundles.list()
location = cogni.doc_bundles.locate(bundle.bundle_id)
```

All returned objects are canonical models from the underlying component
repositories.
