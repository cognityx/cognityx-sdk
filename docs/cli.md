# Unified `cogni` CLI

## Organize Original Files

A SourceAsset is a recorded original file. A DocBundle is a named collection,
similar to a folder.

```bash
cogni bundle create research/reports
cogni bundle list
cogni bundle locate bun-...

cogni asset add report.pdf --bundle research/reports
cogni asset add ./incoming --bundle research --structure preserve
cogni asset list --bundle research/reports
cogni asset show src-...
cogni asset locate src-...
```

## Ingest PDFs

The project chooses how PDFs are read once, while the user supplies only the
document. The normal command is:

```bash
cogni ingest document.pdf
```

The same command also accepts a directory, an existing asset ID, or a complete
bundle path:

```bash
cogni ingest report.pdf
cogni ingest ./reports
cogni ingest --asset src-...
cogni ingest --bundle research/reports
```

The response includes the run ID, job ID, document IDs, asset IDs, page counts,
and stable artifact addresses. DataForge users do not need to select internal
metadata files.

## Configure Ingest Once

Create `.cognityx/ingest.toml` in the project:

```toml
[ingest]
parser_policy = "compare"
parser_backends = ["pymupdf", "docling", "basic"]

[ingest.inference]
enabled = false
```

`compare` asks each installed reader for observed facts and lets Ingest combine
the complementary results. This combination is technically called parser
fusion. `basic` remains last so a PDF can still be handled when the optional
rich readers are unavailable.

Install all configured rich readers with:

```bash
pip install "cognityx[rich-ingest]"
```

Inspect or validate the effective settings before a run:

```bash
cogni ingest-config show
cogni ingest-config validate
```

`show` reports each effective value and whether it came from the command line,
environment-selected file, project file, user file, or built-in defaults. It
does not print inference credentials or the contents of an inference target
file.

It also reports an adaptive routing classification as `planning-only`. This is
an explanation of the active parser policy, not another execution setting. The
current executable controls remain `parser_policy`, `parser_backends`, and
`ingest.inference.enabled`. A `[ingest.routing]` table is rejected because the
merged application path cannot yet execute all three adaptive modes.

Values are resolved independently in this order:

```text
CLI override
> COGNITYX_INGEST_CONFIG file
> .cognityx/ingest.toml
> ~/.config/cognityx/ingest.toml
> built-in fixed/basic defaults
```

`$XDG_CONFIG_HOME/cognityx/ingest.toml` replaces the shown user path when
`XDG_CONFIG_HOME` is set. A missing configuration file is safe: Ingest uses the
Basic reader with inference disabled.

## Monitor Work

```bash
cogni job list
cogni job status <job-id>
cogni job events <job-id>
cogni job watch <job-id>
cogni job cancel <job-id>
```

`events` replays ordered progress. `watch` reconnects at an event sequence and
continues until the job ends. Cancellation is checked between PDFs; the current
PDF parse remains synchronous.

## Inspect Generated Results

```bash
cogni run list
cogni run show <run-id>
cogni run locate <run-id>
cogni document list
cogni document show <document-id>
cogni document locate <document-id>
cogni artifact locate <document-id> provenance
cogni artifact read <document-id> provenance
cogni artifact read <document-id> evidence
cogni artifact read <document-id> canonical-content
cogni artifact read <document-id> source-graph
cogni artifact read <document-id> provenance-addresses
cogni artifact available <document-id>
cogni provenance resolve <document-id> <address-id>
```

`artifact locate` returns a canonical
`storage://<profile>/<logical-key>` URI and safe metadata:

```text
{
  "uri": "storage://local-main/artifacts/ingest/documents/<id>/provenance.json",
  "backend": "LocalStorageBackend",
  "role": "artifact",
  "exists": true,
  "size_bytes": 12345
}
```

The artifact facade never returns a physical local path. `document locate` and
`run locate` retain their older broader diagnostic shape for compatibility;
new automation should prefer the bounded artifact facade.

Supported artifact names are `document`, `evidence`, `provenance`, `manifest`,
`canonical-content`, `source-graph`, `provenance-addresses`,
`parser-observations`, and `parser-fusion-decisions`. The last two appear only
when the selected parser policy produced them. Raw parser-native payloads and
arbitrary Storage keys are not part of this surface.

`artifact read` is unchanged and still returns the artifact payload; `locate` only
returns metadata.

`provenance resolve` reads the document's own Source Graph and address catalog,
validates them, and resolves one exact ID. Its status is one of `exact`,
`redirected`, `ambiguous`, `obsolete`, `forbidden`, or `unresolved`. A forbidden
result never contains protected target details. Resolution does not reopen the
PDF, load parser-native bytes, or start a model.

## Parser Policy And Adaptive Planning

The five legacy parser policies are executable today because `Cogni` passes them
to Ingest's `ParserRouter`:

- `fixed`, `rule`, `fallback`, `compare`, and `agent` can change parser execution.
- `deterministic` has a planning API, but no current `Cogni` plan-to-router bridge.
- `hybrid` has a planning API, requires an injected proposal provider, and has no
  concrete provider or current `Cogni` execution bridge.
- `llm-directed` has a planning API, requires an injected proposal provider, and
  has no concrete provider or current `Cogni` execution bridge.

The live parser capability registry can describe available parsers, but normal
SDK ingestion still constructs the established `ParserRouter` directly. The
compatibility adapter refuses plans whose scope, purpose, stop condition, tags,
or provider requirements would be lost, so the SDK does not silently map
`llm-directed` to `agent`.

## Delete Safely

```bash
# Logical deletion; raw bytes are retained while referenced.
cogni asset delete src-... --yes --reason "superseded"
cogni bundle delete bun-... --recursive --yes

# Generated output deletion; SourceAsset bytes and job history remain.
cogni run delete <run-id> --yes
cogni document delete <document-id> --yes

# Storage-owned physical cleanup. Planning is the default.
cogni cleanup blobs --older-than 7d
cogni cleanup blobs --older-than 7d --yes
```

Storage rechecks every candidate before physical deletion. A future
always-running Storage service will execute this same safe cleanup process
automatically according to retention policy.

## Context And Advanced Storage Configuration

Normal commands load the configured Storage Runtime automatically:

```bash
cogni ingest report.pdf --tenant-id acme --project-id research
```

An operator may select a configuration explicitly:

```bash
cogni ingest report.pdf --storage-config .cognityx/storage.toml
```

Parser flags remain advanced, one-run overrides. Explicit flags take priority
over configuration:

```bash
cogni ingest report.pdf \
  --parser-policy fixed \
  --parser-backend pymupdf \
  --inference-config .cognityx/ingest-inference.toml
```

The Inference file contains an operator-approved target list and explicitly
enables bounded inference for that run. For local work,
its named server profile starts the worker and loads the configured model.
Only unresolved provenance tasks are sent, calls and tokens are bounded, and
invented anchors are rejected. DataForge users do not need these options.
When `ingest.inference.enabled` is `true` in project configuration, an operator
must provide that target file through `COGNITYX_INGEST_INFERENCE_CONFIG`.

Successful stdout is JSON. Diagnostics go to stderr. Exit codes are `0` for
success, `1` for operational failure, `2` for arguments or missing
confirmation, `3` for inaccessible resources, and `4` for authorization
rejection.

## Deprecated / Compatibility

The component-level `cognityx-ingest` command; plural `assets`, `doc-bundles`,
`jobs`, `runs`, `documents`, and `artifacts`; historical `sources` and
`bundles`; `jobs show`; ID-only `--bundle-id`; and `--storage-root` remain
temporarily available. New scripts use singular resource commands, bundle
paths, and normal Storage Runtime loading.

The standalone `cognityx-ingest` CLI is compatibility-only and may expose fewer
inspection names. Use `cogni` for the v3.2 user-facing read and resolution APIs.

The old generated `source.pdf` artifact is not available. Use `cogni asset
show` or `cogni asset locate` for the original SourceAsset.
