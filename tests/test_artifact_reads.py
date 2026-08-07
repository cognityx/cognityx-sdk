"""Verify the two-layer trust boundary for settled SDK artifact reads.

These production-facing tests ingest real documents through ``Cogni`` and use
the merged Ingest manager rather than an SDK-only authorization substitute.  The
suite proves that closed public names and exact manifest URIs are checked first,
then exact artifact policy is enforced before component Storage access.  Python
and CLI callers are covered, including denial redaction, optional settled files,
legacy names, and path/URI/raw-parser rejection without inference startup.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from cognityx import Cogni
from cognityx.artifacts import ARTIFACT_NAMES
from cognityx.cli import main
from cognityx_ingest.control import (
    INGEST_RESULT_READ,
    ControlDecision,
    IngestAuthorizationError,
)
from cognityx_resource import ResourceContext
from cognityx_storage import StorageConfig, StorageRuntime


def _write_text_pdf(path: Path, text: str) -> None:
    """Write one deterministic text PDF using only the test dependency stack."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_ref}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as destination:
        writer.write(destination)


class _TenantControl:
    """Deny reads outside one tenant for authorization-boundary assertions."""

    def authorize(self, context, action=None, resource=None, request=None):
        return ControlDecision(
            allowed=context.tenant_id == "tenant-a",
            reason="tenant mismatch",
        )

    def report_usage(self, context, usage) -> None:
        return None


class _ArtifactPolicyControl:
    """Record component policy requests and deny selected artifact byte reads.

    SDK security tests inject this narrow ``ControlClient`` into the real
    composition root.  Metadata resources remain allowed while exact resources
    carrying an ``artifact`` member can be denied independently.  The mutable
    denied set models a policy update after ingestion; calls are retained only for
    deterministic assertions, and production Ingest still owns authorization
    ordering, typed failures, and Storage access.
    """

    def __init__(self) -> None:
        """Start with all operations allowed and an empty ordered call journal."""
        self.denied_artifacts: set[str] = set()
        self.calls: list[tuple[str | None, dict[str, object]]] = []

    def authorize(
        self,
        context: Any,
        action: str | None = None,
        resource: dict[str, object] | None = None,
        request: object | None = None,
    ) -> ControlDecision:
        """Return a decision based only on the exact requested artifact name.

        Ingest calls this synchronously before protected component operations.
        The method copies the resource for later assertions, denies only configured
        artifact reads, and otherwise allows metadata and ingest lifecycle work.
        It performs no I/O, mutation beyond the test journal, or request parsing;
        concurrent use is intentionally outside this single-threaded test double.
        """
        captured = dict(resource or {})
        self.calls.append((action, captured))
        artifact = captured.get("artifact")
        denied = isinstance(artifact, str) and artifact in self.denied_artifacts
        return ControlDecision(
            allowed=not denied,
            reason=f"artifact {artifact} denied" if denied else None,
        )

    def report_usage(self, context: Any, usage: object) -> None:
        """Accept usage reports without adding an unrelated accounting seam."""
        return None

    def deny(self, *names: str) -> None:
        """Replace the denied artifact set for the next synchronous assertion."""
        self.denied_artifacts = set(names)

    def mark(self) -> int:
        """Return a stable journal offset without clearing prior component calls."""
        return len(self.calls)

    def resources_since(self, mark: int) -> list[dict[str, object]]:
        """Return copied resources recorded after one previously captured offset."""
        return [resource for _action, resource in self.calls[mark:]]


@pytest.fixture
def ingested_document(tmp_path: Path):
    """Return one real local Cogni root and its deterministic document ID."""
    source = tmp_path / "policy.pdf"
    _write_text_pdf(source, "Cognityx settled artifact contract")
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="tenant-a", principal_id="alice"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )
    result = cogni.ingest_path(source)
    return cogni, result.results[0].document.document_id, tmp_path / "storage"


def _ingested_with_artifact_policy(
    tmp_path: Path,
) -> tuple[Cogni, str, Path, _ArtifactPolicyControl]:
    """Create one real merged-Ingest document under artifact-aware test policy.

    Authorization tests use this helper to run normal PDF ingestion before
    changing the policy for reads.  It returns the public SDK root, canonical
    document ID, private test-only Storage root, and recording control client.
    Construction writes only beneath ``tmp_path`` and starts no inference model.
    """
    source = tmp_path / "protected-policy.pdf"
    _write_text_pdf(source, "Protected source graph bytes must never leak")
    root = tmp_path / "storage"
    control = _ArtifactPolicyControl()
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="tenant-a", principal_id="alice"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=root)
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
        control=control,
    )
    document_id = cogni.ingest_path(source).results[0].document.document_id
    return cogni, document_id, root, control


def test_settled_artifact_reads_and_locations_are_closed_and_path_free(
    ingested_document,
) -> None:
    cogni, document_id, _root = ingested_document

    available = cogni.artifacts.available(document_id)
    assert available[:7] == ARTIFACT_NAMES[:7]
    assert json.loads(cogni.artifacts.read(document_id, "canonical-content"))
    assert json.loads(cogni.artifacts.read(document_id, "source-graph"))
    assert json.loads(cogni.artifacts.read(document_id, "provenance-addresses"))
    assert cogni.artifacts.read(document_id, "provenance")
    location = cogni.artifacts.locate(document_id, "source-graph")
    assert location["location"]["uri"].startswith("storage://")
    assert "local_path" not in location["location"]
    assert str(_root) not in json.dumps(location)


@pytest.mark.parametrize(
    "name",
    (
        "missing",
        "../../manifest",
        "file:///tmp/secret",
        "storage://other/key",
        "source_graph",
        "parser/pymupdf",
    ),
)
def test_artifact_names_reject_unknown_traversal_and_arbitrary_uris(
    ingested_document, name: str
) -> None:
    """Reject non-public names before manifest resolution or byte access."""
    cogni, document_id, _root = ingested_document
    with pytest.raises(ValueError, match="Unknown artifact"):
        cogni.artifacts.read(document_id, name)


@pytest.mark.parametrize("name", ("source-graph", "provenance-addresses"))
def test_v3_2_artifact_reads_reuse_document_authorization(
    tmp_path: Path, name: str
) -> None:
    source = tmp_path / "policy.pdf"
    _write_text_pdf(source, "Authorization boundary")
    runtime = StorageRuntime.from_config(
        StorageConfig.built_in(root=tmp_path / "storage")
    )
    writer = Cogni.load(
        context=ResourceContext(tenant_id="tenant-a"),
        storage_runtime=runtime,
        catalog_path=tmp_path / "catalog.sqlite3",
        control=_TenantControl(),
    )
    document_id = writer.ingest_path(source).results[0].document.document_id
    reader = Cogni.load(
        context=ResourceContext(tenant_id="tenant-b"),
        storage_runtime=runtime,
        catalog_path=tmp_path / "catalog.sqlite3",
        control=_TenantControl(),
    )

    with pytest.raises(IngestAuthorizationError, match="tenant mismatch"):
        reader.artifacts.read(document_id, name)


def test_manifest_uri_must_match_the_fixed_configured_artifact_uri(
    ingested_document, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a foreign manifest URI before delegating any component byte read."""
    cogni, document_id, root = ingested_document
    manifest_path = root / "artifacts/ingest/documents" / document_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["source_graph"]["uri"] = "storage://foreign/key"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def unexpected_component_read(
        context: Any, selected_document: str, name: str
    ) -> bytes:
        """Fail if SDK integrity validation incorrectly reaches byte authorization."""
        pytest.fail(
            "IngestManager.read_artifact was called after a forged manifest URI"
        )

    monkeypatch.setattr(
        cogni.ingest_manager, "read_artifact", unexpected_component_read
    )

    with pytest.raises(ValueError, match="configured Storage URI"):
        cogni.artifacts.read(document_id, "source-graph")


def test_artifact_byte_denial_crosses_the_real_ingest_manager(tmp_path: Path) -> None:
    """Prove metadata permission cannot authorize protected source-graph bytes."""
    cogni, document_id, _root, control = _ingested_with_artifact_policy(tmp_path)
    control.deny("source-graph")
    mark = control.mark()

    with pytest.raises(IngestAuthorizationError, match="source-graph denied"):
        cogni.artifacts.read(document_id, "source-graph")

    assert control.resources_since(mark) == [
        {"document_id": document_id},
        {"document_id": document_id, "artifact": "source-graph"},
    ]
    assert [action for action, _resource in control.calls[mark:]] == [
        INGEST_RESULT_READ,
        INGEST_RESULT_READ,
    ]


def test_cli_artifact_denial_returns_existing_exit_without_content_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise public CLI failure handling for exact artifact authorization."""
    cogni, document_id, root, control = _ingested_with_artifact_policy(tmp_path)
    control.deny("source-graph")
    mark = control.mark()
    monkeypatch.setattr("cognityx.cli._load", lambda _args: cogni)

    code = main(["artifact", "read", document_id, "source-graph"])
    captured = capsys.readouterr()

    assert code == 4
    assert captured.out == ""
    assert "source-graph denied" in captured.err
    assert "Protected source graph bytes" not in captured.err
    assert str(root) not in captured.err
    assert control.resources_since(mark) == [
        {"document_id": document_id},
        {"document_id": document_id, "artifact": "source-graph"},
    ]


def test_every_present_public_artifact_read_delegates_to_ingest_manager(
    ingested_document, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove all nine public names use component-owned byte reads when present."""
    cogni, document_id, root = ingested_document
    document_root = root / "artifacts/ingest/documents" / document_id
    manifest_path = document_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    optional = {
        "parser-observations": ("parser_observations", "parser/observations.json"),
        "parser-fusion-decisions": (
            "parser_fusion_decisions",
            "parser/fusion-decisions.json",
        ),
    }
    for _name, (manifest_name, filename) in optional.items():
        path = document_root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}")
        key = f"ingest/documents/{document_id}/{filename}"
        manifest["artifacts"][manifest_name] = {
            "uri": cogni.storage.for_role("artifact").uri(key)
        }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    manager = cogni.ingest_manager
    component_read = manager.read_artifact
    delegated: list[tuple[str, str]] = []

    def recording_read(context: Any, selected_document: str, name: str) -> bytes:
        """Journal delegation, then invoke the bound merged component operation."""
        delegated.append((selected_document, name))
        return component_read(context, selected_document, name)

    monkeypatch.setattr(manager, "read_artifact", recording_read)

    for name in ARTIFACT_NAMES:
        assert isinstance(cogni.artifacts.read(document_id, name), bytes)

    assert delegated == [(document_id, name) for name in ARTIFACT_NAMES]
