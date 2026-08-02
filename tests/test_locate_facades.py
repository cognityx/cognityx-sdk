from __future__ import annotations

import pytest

from cognityx.artifacts import Artifacts
from cognityx.documents import Documents
from cognityx.runs import Runs
from cognityx_storage import StorageLocation


class _FakeExecution:
    run_id = "run-placeholder"


class _FakeRuntime:
    def __init__(self, locations: dict[str, StorageLocation]):
        self._locations = locations
        self.seen: list[str] = []

    def locate(self, uri: str) -> StorageLocation:
        self.seen.append(uri)
        return self._locations[uri]


class _FakeIngestManager:
    def __init__(self, documents: dict, runs: dict) -> None:
        self._documents = documents
        self._runs = runs

    def show_document(self, execution, document_id: str):
        return self._documents[document_id]

    def show_run(self, execution, run_id: str):
        return self._runs[run_id]


class _FakeOwner:
    def __init__(self, *, storage, ingest_manager) -> None:
        self.storage = storage
        self.ingest_manager = ingest_manager

    def new_execution(self) -> _FakeExecution:
        return _FakeExecution()


def _location(uri: str, *, role: str, exists: bool, local_path: str | None) -> StorageLocation:
    return StorageLocation(
        uri=uri,
        backend_name="_SyntheticRemoteBackend" if local_path is None else "LocalStorageBackend",
        profile_name="local-main" if local_path is not None else "remote-main",
        role_name=role,
        local_path=local_path,
        exists=exists,
        size_bytes=123 if exists else None,
    )


def _owner() -> tuple[_FakeOwner, _FakeRuntime, dict, dict]:
    document_id = "pdf-example"
    run_id = "run-example"
    document_uri_prefix = "storage://local-main/artifacts/ingest/documents/pdf-example"
    document = {
        "manifest": {
            "artifacts": {
                "document": {"uri": f"{document_uri_prefix}/document.json"},
                "evidence": {"uri": f"{document_uri_prefix}/evidence.jsonl"},
                "provenance": {"uri": f"{document_uri_prefix}/provenance.json"},
                "parser/pymupdf": {"uri": f"{document_uri_prefix}/parser/pymupdf.json"},
            }
        }
    }
    run = {
        "document_manifest_refs": [
            f"{document_uri_prefix}/manifest.json",
            f"{document_uri_prefix}/appendix/manifest.json",
        ],
        "evidence_refs": [f"{document_uri_prefix}/evidence.jsonl"],
        "provenance_refs": [f"{document_uri_prefix}/provenance.json"],
    }
    locations = {
        f"{document_uri_prefix}/document.json": _location(
            f"{document_uri_prefix}/document.json", role="artifact", local_path="/tmp/document.json", exists=True
        ),
        f"{document_uri_prefix}/evidence.jsonl": _location(
            f"{document_uri_prefix}/evidence.jsonl", role="artifact", local_path="/tmp/evidence.jsonl", exists=True
        ),
        f"{document_uri_prefix}/parser/pymupdf.json": _location(
            f"{document_uri_prefix}/parser/pymupdf.json", role="artifact", local_path="/tmp/parser-pymupdf.json", exists=True
        ),
        f"{document_uri_prefix}/provenance.json": _location(
            f"{document_uri_prefix}/provenance.json", role="artifact", local_path="/tmp/provenance.json", exists=True
        ),
        f"{document_uri_prefix}/manifest.json": _location(
            f"{document_uri_prefix}/manifest.json", role="artifact", local_path="/tmp/manifest.json", exists=True
        ),
        f"{document_uri_prefix}/appendix/manifest.json": _location(
            f"{document_uri_prefix}/appendix/manifest.json", role="artifact", local_path=None, exists=False
        ),
    }
    runtime = _FakeRuntime(locations)
    owner = _FakeOwner(storage=runtime, ingest_manager=_FakeIngestManager({document_id: document}, {run_id: run}))
    return owner, runtime, {document_id: document}, {run_id: run}


def test_sdk_facade_locates_artifacts_with_authoritative_uris() -> None:
    owner, runtime, _, _ = _owner()
    artifacts = Artifacts(owner)
    manifest = artifacts.locate("pdf-example", "provenance")
    assert runtime.seen == [manifest["location"]["uri"]]
    assert manifest["location"]["uri"].endswith("/provenance.json")
    assert manifest["name"] == "provenance"
    assert "secret" not in str(manifest["location"]).lower()


def test_sdk_facade_returns_document_locate_payload_with_run_artifacts_ordered() -> None:
    owner, runtime, _, _ = _owner()
    documents_api = Documents(owner)
    located = documents_api.locate("pdf-example")

    assert "manifest" not in located["artifacts"]
    assert located["artifacts"]["provenance"]["backend"] == "LocalStorageBackend"
    assert located["artifacts"]["provenance"]["backend"] == "LocalStorageBackend"
    assert located["artifacts"]["parser/pymupdf"]["backend"] == "LocalStorageBackend"
    assert runtime.seen == [
        "storage://local-main/artifacts/ingest/documents/pdf-example/document.json",
        "storage://local-main/artifacts/ingest/documents/pdf-example/evidence.jsonl",
        "storage://local-main/artifacts/ingest/documents/pdf-example/provenance.json",
        "storage://local-main/artifacts/ingest/documents/pdf-example/parser/pymupdf.json",
    ]


def test_sdk_facade_run_locate_preserves_artifact_order_and_reports_missing() -> None:
    owner, runtime, _, runs = _owner()
    located = Runs(owner).locate("run-example")

    assert list(located["artifacts"].keys())[0] == "document_manifest[0]"
    assert list(located["artifacts"].keys())[1] == "document_manifest[1]"
    assert list(located["artifacts"].keys())[2] == "evidence[0]"
    assert list(located["artifacts"].keys())[3] == "provenance[0]"
    assert located["run_id"] == "run-example"
    assert located["artifacts"]["document_manifest[1]"]["exists"] is False
    assert located["artifacts"]["document_manifest[0]"]["exists"] is True
    assert located["artifacts"]["evidence[0]"]["exists"] is True
    assert runtime.seen and all(item in runtime.seen for item in runs["run-example"]["evidence_refs"])
    assert all("secret" not in str(item).lower() for item in located["artifacts"].values())


def test_sdk_facade_locate_keeps_unknown_ids_and_artifact_inputs_strict() -> None:
    owner, _, _, _ = _owner()
    with pytest.raises(KeyError):
        Documents(owner).locate("missing-document")

    with pytest.raises(KeyError):
        Runs(owner).locate("missing-run")


def test_sdk_locate_raises_for_unknown_artifact_without_fabricating_paths() -> None:
    owner, _, _, _ = _owner()
    with pytest.raises(ValueError, match="choose one of"):
        Artifacts(owner).locate("pdf-example", "missing")


def test_sdk_facade_locates_parser_artifact() -> None:
    owner, runtime, _, _ = _owner()
    parser = Artifacts(owner).locate("pdf-example", "parser/pymupdf")
    assert parser["name"] == "parser/pymupdf"
    assert parser["location"]["uri"].endswith("/parser/pymupdf.json")
    assert runtime.seen[-1] == parser["location"]["uri"]
