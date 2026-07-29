# Concepts

`Cogni` is a thin application-facing facade. It composes existing Cognityx
components and returns their canonical models.

- `ResourceContext` is the stable governance and ownership context.
- Each action creates a fresh `ExecutionContext` for tracing and control. A
  complete folder registration is one action and uses one execution for every
  discovered file.
- `Assets` exposes SourceAsset registration and retrieval.
- `DocBundles` exposes logical SourceAsset groupings.

The SDK does not own Context persistence, Blob/CAS, deduplication, catalog
storage, domain authorization, or filesystem traversal. Directory discovery
and batch registration belong to `cognityx-ingest`; the SDK only delegates.
