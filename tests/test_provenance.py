"""Production-facing tests for deterministic SDK provenance resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognityx import Cogni
from cognityx.provenance import _resolution_dict
from cognityx_ingest import AddressResolution, SourceGraphRevisionError
from cognityx_resource import ResourceContext
from cognityx_storage import StorageConfig, StorageRuntime

from test_artifact_reads import _write_text_pdf


def _root(tmp_path: Path) -> Cogni:
    """Construct one local SDK root whose artifact paths stay test-internal."""
    return Cogni.load(
        context=ResourceContext(tenant_id="tenant-a"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )


def _ingest(cogni: Cogni, path: Path, text: str) -> tuple[str, str]:
    """Ingest text and return its document ID plus first generated strong address."""
    _write_text_pdf(path, text)
    document_id = cogni.ingest_path(path).results[0].document.document_id
    catalog = json.loads(
        cogni.artifacts.read(document_id, "provenance-addresses")
    )
    return document_id, catalog["strong_addresses"][0]["address_id"]


def test_resolver_uses_own_document_graph_and_never_initializes_inference(
    tmp_path: Path,
) -> None:
    cogni = _root(tmp_path)
    first_id, first_address = _ingest(
        cogni, tmp_path / "first.pdf", "First document evidence"
    )
    second_id, _second_address = _ingest(
        cogni, tmp_path / "second.pdf", "Different document evidence"
    )
    service = cogni._ingest_service
    assert service is not None and service._resolver is None

    exact = cogni.provenance.resolve(first_id, first_address)
    foreign = cogni.provenance.resolve(second_id, first_address)

    assert exact["status"] == "exact"
    assert exact["target"]
    assert foreign["status"] == "unresolved"
    assert "target" not in foreign
    assert cogni._ingest_service is service
    assert service._resolver is None


def test_forged_source_graph_revision_fails_through_sdk(
    tmp_path: Path,
) -> None:
    cogni = _root(tmp_path)
    document_id, address_id = _ingest(
        cogni, tmp_path / "forged.pdf", "Revision integrity"
    )
    graph_path = (
        tmp_path
        / "storage/artifacts/ingest/documents"
        / document_id
        / "source-graph.json"
    )
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["graph_revision"] = "sg-" + ("0" * 64)
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    with pytest.raises(SourceGraphRevisionError):
        cogni.provenance.resolve(document_id, address_id)


def test_forbidden_projection_contains_no_target_or_candidate_details() -> None:
    payload = _resolution_dict(
        AddressResolution(
            address_id="addr-protected",
            status="forbidden",
            reason="Access policy denied this address",
            graph_revision="sg-protected",
        )
    )

    assert payload["status"] == "forbidden"
    assert set(payload) == {"address_id", "status", "reason", "graph_revision"}
