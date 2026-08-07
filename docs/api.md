# API

## Loading

```python
from cognityx import Cogni

cogni = Cogni.load()
```

`Cogni.load()` resolves `.cognityx/ingest.toml` with the same precedence as the
CLI. The resolved, secret-free values and their sources are available as
`cogni.ingest_configuration`.

Advanced callers may provide `context`, `context_file`, `context_overrides`,
`cwd`, `user_context_file`, `storage_runtime`, `storage_config`,
`catalog_path`, `jobs_database`, `inference_config`, `parser_policy`,
`parser_backends`, `inference_enabled`, `user_ingest_config_file`, and an
Ingest `control` client. Explicit parser values override discovered
configuration. Conflicting context or Storage arguments are rejected.

`cogni.ingest_configuration.to_dict()` includes a derived adaptive routing term
with `execution_active: false`. It explains how the executable legacy policy is
classified by the v3.2 planner; it is not an accepted setting and does not claim
that an adaptive plan reaches parser execution.

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

Add a complete directory with one batch `ExecutionContext`:

```python
result = cogni.assets.add(
    "/data/contracts",
    bundle="legal",
    structure="preserve",
)

print(result.batch_id)
print(result.created_count, result.failed_count)
for item in result.items:
    print(item.relative_path, item.bundle_path, item.status)
```

For directories, `preserve` recreates relative folders as DocBundles and
`flat` places all files in the root DocBundle. Set `recursive=False` to use
only direct child files. A file continues to return
`SourceAssetRegistrationResult`; a directory returns
`SourceAssetBatchResult`.

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

## Ingest

Project configuration keeps the Python call configuration-first too:

```toml
[ingest]
parser_policy = "compare"
parser_backends = ["pymupdf", "docling", "basic"]

[ingest.inference]
enabled = false
```

```python
path_run = cogni.ingest_path("report.pdf")
asset_run = cogni.ingest_asset("src-...")
bundle_run = cogni.ingest_bundle("bun-...")
bundle_path_run = cogni.ingest_bundle_path("legal/hr")

print(path_run.run_id, path_run.job_id)
for result in path_run.results:
    print(result.document.document_id, len(result.evidence))
```

Use `cogni.ingest_manager` for advanced job, run, and document administration.
Use the bounded artifact facade for normal generated-output inspection:

```python
names = cogni.artifacts.available(document_id)
graph_bytes = cogni.artifacts.read(document_id, "source-graph")
location = cogni.artifacts.locate(document_id, "provenance-addresses")
```

Names come from a closed public vocabulary. Reads authorize the document,
verify its manifest against the configured logical Storage URI, and return exact
bytes. Location output deliberately omits physical paths.

Resolve a stable evidence address with the same document-owned artifacts:

```python
resolution = cogni.provenance.resolve(document_id, address_id)
print(resolution["status"])
```

The resolver preserves `exact`, `redirected`, `ambiguous`, `obsolete`,
`forbidden`, and `unresolved`. It returns accepted or candidate targets only when
the Ingest resolver permits them. It never returns source text and does not need
the original PDF, parser-native bytes, inference, or a network connection.

## Blob cleanup

```python
from datetime import timedelta

plan = cogni.cleanup.plan_blobs(older_than=timedelta(days=7))

# Planning never deletes physical objects.
result = cogni.cleanup.execute_blobs(plan, batch_size=100)
```

All returned objects are canonical models from the underlying component
repositories.
