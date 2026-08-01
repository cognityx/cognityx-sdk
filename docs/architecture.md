# Architecture

```text
Application
    ↓
Cogni
    ↓
cognityx-resource · cognityx-storage · cognityx-ingest · cognityx-jobs
```

`Cogni.load()` resolves one stable `ResourceContext` and one
`StorageRuntime`. The SourceAsset registry is initialized only when
`cogni.assets`, `cogni.doc_bundles`, or the advanced
`cogni.source_asset_registry` property is first used. Ingest, Assets,
DocBundles, Jobs, generated-result management, and cleanup share the same
Context, Storage runtime, and Control client.

Every action creates a new `ExecutionContext` from the stable Context. The
catalog path, capability checks, legacy selection, Blob ownership, and
deduplication remain owned by Ingest and Storage.

The unified CLI follows the same route:

```text
cogni CLI
    ↓
Cogni
    ↓
Assets · DocBundles · Ingest · Jobs · Documents · Cleanup
    ↓
Ingest and Storage component APIs
```

It does not create a separate persistence or cleanup orchestration path.

## Diagnostics

```python
print(cogni.describe())
```

The result contains non-secret context, Storage diagnostics, and catalog
information after lazy registry initialization.
