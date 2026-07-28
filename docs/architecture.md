# Architecture

```text
Application
    ↓
Cogni
    ↓
cognityx-resource · cognityx-storage · cognityx-ingest
```

`Cogni.load()` resolves one stable `ResourceContext` and one
`StorageRuntime`. The SourceAsset registry is initialized only when
`cogni.assets`, `cogni.doc_bundles`, or the advanced
`cogni.source_asset_registry` property is first used. Both namespaces share
the same registry instance.

Every action creates a new `ExecutionContext` from the stable Context. The
catalog path, capability checks, legacy selection, Blob ownership, and
deduplication remain owned by Ingest and Storage.

## Diagnostics

```python
print(cogni.describe())
```

The result contains non-secret context, Storage diagnostics, and catalog
information after lazy registry initialization.
