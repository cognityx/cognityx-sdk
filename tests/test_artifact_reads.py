"""Security and compatibility tests for settled SDK artifact reads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from cognityx import Cogni
from cognityx.artifacts import ARTIFACT_NAMES
from cognityx_ingest.control import ControlDecision, IngestAuthorizationError
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
    ("missing", "../../manifest", "file:///tmp/secret", "storage://other/key"),
)
def test_artifact_names_reject_unknown_traversal_and_arbitrary_uris(
    ingested_document, name: str
) -> None:
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
    ingested_document,
) -> None:
    cogni, document_id, root = ingested_document
    manifest_path = root / "artifacts/ingest/documents" / document_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["source_graph"]["uri"] = "storage://foreign/key"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="configured Storage URI"):
        cogni.artifacts.read(document_id, "source-graph")
