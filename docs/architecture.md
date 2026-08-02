# Architecture

```text
Application
    ↓
Cogni
    ↓
cognityx-resource · cognityx-storage · cognityx-ingest · cognityx-jobs
                                      · optional cognityx-inference
```

`Cogni.load()` resolves one stable `ResourceContext`, one `StorageRuntime`, and
one effective Ingest configuration. Ingest settings are layered from safe
built-in values through user, project, environment-selected, and explicit CLI
values. The resulting parser policy still enters the existing Ingest
`ParserRouter`; the SDK does not implement a second parsing path.

The SourceAsset registry is initialized only when the
`cogni asset` or `cogni bundle` command, the Python `cogni.assets` or
`cogni.doc_bundles` facade, or the advanced `cogni.source_asset_registry`
property is first used. Ingest, Assets,
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

When bounded resolution is configured, `Cogni` constructs the existing
`CognityxInferenceClient`. A named local server profile starts the worker and
loads its approved model. Provider/model capability checks occur before an
external request. Ingest records the request identity and validates every
proposed source anchor before publishing provenance.

## Diagnostics

```python
print(cogni.describe())
```

The result contains non-secret context, effective Ingest settings, Storage
diagnostics, and catalog information after lazy registry initialization.
