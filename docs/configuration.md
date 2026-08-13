# Understand effective configuration

The SDK brings several Cognityx components together, but it does not own one
global master configuration file. In plain terms, Ingest chooses how documents
are read, Storage chooses where durable data goes, and Resource Context chooses
who and which project the work belongs to. Each owner keeps its own master.

```text
Resource Context ─┐
Storage ──────────┼─> Cogni / cogni ─> Ingest operations
Ingest settings ──┘
```

## Static commands

```bash
cogni config show [--component all|ingest|storage|context]
cogni config validate [--component all|ingest|storage|context]
```

Both commands emit deterministic JSON and use the same pure resolvers as real
execution. They do not create a catalog or Jobs database, construct a parser,
open Storage, load a model, contact a provider, or make a network call.

Add `--human` to read the same secret-safe report as labelled text. JSON remains
the default for automation, and rendering the readable form does not resolve
configuration again.

The report distinguishes the highest-precedence file actually loaded
(`master_config`), every loaded file in low-to-high order (`config_layers`),
where values came from (`field_sources`), explicit values that really changed
the result (`overrides`), and the final secret-safe values (`effective`).

Catalog and Jobs database paths appear under `runtime_selections`. They are
locations chosen for this process, not master configuration files.

## Ingest layering

Ingest retains its existing low-to-high order: built-ins, user settings,
project `.cognityx/ingest.toml`, `COGNITYX_INGEST_CONFIG`, and an explicit
`--ingest-config PATH`. Parser policy/backend flags are final value overrides.
The equivalent Python selector is `Cogni.load(ingest_config=...)`.

`cogni ingest-config show|validate` remains as the compatibility Ingest-only
view. New automation should use `cogni config` for the full provenance report.

An explicit `--inference-config` is a bounded runtime selection. Inspection
parses and validates that file, records its hash, and stops without creating an
Inference client. A file's mere presence is never converted into an unchecked
`inference_enabled=true` claim.

## Storage and Context

Storage and Resource Context reports come from their owner packages. Storage
preserves explicit, environment, project, user, then built-in selection.
Context preserves explicit, environment, project, user, then built-in selection
and reports only field or scope arguments that changed a value.

Experiment configuration has its own owner and can be inspected through the
SDK without loading the broader application runtime:

```bash
cogni experiment config show [--storage-config PATH | --storage-root PATH]
cogni experiment config validate [--storage-config PATH | --storage-root PATH]
```

These commands delegate to Cognityx Experiments. Add `--human` for readable
text; omit it for the component's unchanged JSON report.

## What remains explicit

Research YAML, DataForge build recipes, Training and autotune specifications,
evaluation requests, boundary-search configurations, judge methods, manifests,
model revisions, and publication artifacts are scientific or runtime inputs.
They are not ambiently discovered by `Cogni.load()`.
