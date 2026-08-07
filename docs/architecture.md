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
Assets · DocBundles · Ingest · Jobs · Documents · Artifacts · Provenance · Cleanup
    ↓
Ingest and Storage component APIs
```

It does not create a separate persistence or cleanup orchestration path.

Artifact reads first ask `IngestManager` to authorize and load the document
manifest. The SDK accepts only a fixed public artifact name, derives its fixed
logical filename, and checks that the manifest URI equals the URI produced by
the configured artifact role. Only then does it open or locate the object. This
keeps arbitrary keys, external URLs, traversal strings, and physical paths out
of the user boundary.

Provenance resolution composes that read path twice: once for the Source Graph
and once for its address catalog. Public strict Ingest readers validate both,
including the content-derived graph revision, before the deterministic T08
resolver runs. The graph and catalog cannot be supplied separately, so a caller
cannot substitute another document's evidence.

When bounded resolution is configured, `Cogni` constructs the existing
`CognityxInferenceClient`. A named local server profile starts the worker and
loads its approved model. Provider/model capability checks occur before an
external request. Ingest records the request identity and validates every
proposed source anchor before publishing provenance.

## v3.2 Control Audit

- Parser policy and ordered backends are user-selectable, stable public inputs,
  and consumed by normal parser execution.
- Bounded inference enablement and its approved target file are executable in the
  established `agent`/resolution path.
- Adaptive `deterministic`, `hybrid`, and `llm-directed` modes have planning APIs.
  `hybrid` and `llm-directed` also require an injected proposal provider. No
  concrete merged provider and no `Cogni` plan-to-`ParserRouter` bridge currently
  exist, so none is exposed as an execution selector.
- Segmentation views have a stable domain API, but normal `Cogni.ingest_*` does
  not consume a strategy selection. No no-op setting is exposed.
- Extraction reuse, retention, and purge have stable administrative APIs, but
  normal ingestion does not consume an SDK retention selection. Cleanup remains
  a separate administrative surface.
- Provenance address resolution is a settled deterministic read operation, so it
  is exposed as a facade and command rather than an ingest setting.

The exact known gap is live adaptive parser-selection integration. Completing
it requires a separately reviewed provider and execution bridge; T10 neither
implements that algorithm nor disguises it as the legacy `agent` policy.

## Diagnostics

```python
print(cogni.describe())
```

The result contains non-secret context, effective Ingest settings, Storage
diagnostics, and catalog information after lazy registry initialization.
