from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from cognityx_ingest.control import ControlDecision
from cognityx_ingest.control import IngestAuthorizationError

from cognityx import Cogni
from cognityx_resource import ResourceContext
from cognityx_storage import StorageConfig, StorageRuntime


def _runtime(root: Path) -> StorageRuntime:
    return StorageRuntime.from_config(StorageConfig.built_in(root=root))


def test_load_keeps_context_and_runtime_and_defers_registry(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    context = ResourceContext(tenant_id="acme", principal_id="alice")

    cogni = Cogni.load(
        context=context,
        storage_runtime=runtime,
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    assert cogni.context is context
    assert cogni.context_id == context.context_id
    assert cogni.storage is runtime
    assert cogni._registry is None
    assert not (tmp_path / "catalog.sqlite3").exists()
    assert cogni.describe()["source_asset_catalog"] is None

    assert cogni.assets is cogni.assets
    assert cogni.assets._owner.source_asset_registry is cogni.doc_bundles._owner.source_asset_registry
    assert (tmp_path / "catalog.sqlite3").exists()


def test_cleanup_is_lazy_and_shares_registry_runtime_and_control(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path / "storage")
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme"),
        storage_runtime=runtime,
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    assert cogni._registry is None
    cleanup = cogni.cleanup
    assert cogni._registry is None
    service = cogni.source_asset_cleanup_service

    assert service.registry is cogni.source_asset_registry
    assert service.storage_runtime is runtime
    assert cleanup is cogni.cleanup


def test_context_and_storage_conflicts_are_rejected(tmp_path: Path) -> None:
    context = ResourceContext(tenant_id="acme")
    runtime = _runtime(tmp_path)
    context_file = tmp_path / "context.json"
    context_file.write_text(json.dumps({"tenant_id": "other"}), encoding="utf-8")

    with pytest.raises(ValueError, match="context cannot be combined"):
        Cogni.load(context=context, context_file=context_file)
    with pytest.raises(ValueError, match="context cannot be combined"):
        Cogni.load(context=context, context_overrides={"tenant_id": "other"})
    with pytest.raises(ValueError, match="context cannot be combined"):
        Cogni.load(context=context, user_context_file=context_file)
    with pytest.raises(ValueError, match="either storage_runtime or storage_config"):
        Cogni.load(storage_runtime=runtime, storage_config=context_file)


def test_context_file_and_overrides_delegate_to_resource(tmp_path: Path) -> None:
    context_file = tmp_path / "context.json"
    context_file.write_text(
        json.dumps({"tenant_id": "acme", "project_id": "old"}),
        encoding="utf-8",
    )

    cogni = Cogni.load(
        context_file=context_file,
        context_overrides={"project_id": "research"},
        storage_runtime=_runtime(tmp_path / "storage"),
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    assert cogni.context.tenant_id == "acme"
    assert cogni.context.project_id == "research"


def test_new_execution_is_fresh_but_context_is_stable(tmp_path: Path) -> None:
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme"),
        storage_runtime=_runtime(tmp_path),
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    first, second = cogni.new_execution(), cogni.new_execution()

    assert first.context_id == second.context_id == cogni.context_id
    assert first.run_id != second.run_id
    assert first.correlation_id != second.correlation_id


class _DenyByTenantControl:
    def __init__(self, allowed_tenant: str) -> None:
        self.allowed_tenant = allowed_tenant

    def authorize(self, context, action=None, resource=None, request=None):
        allowed = context.tenant_id == self.allowed_tenant
        return ControlDecision(
            allowed=allowed,
            reason=None if allowed else "tenant mismatch",
        )

    def report_usage(self, context, usage) -> None:
        return None


def test_locate_respects_authorization_boundaries(tmp_path: Path) -> None:
    runtime = StorageRuntime.from_config(StorageConfig.built_in(root=tmp_path / "storage"))
    source = tmp_path / "policy.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as stream:
        writer.write(stream)
    control = _DenyByTenantControl("tenant-a")
    writer_cogni = Cogni.load(
        context_overrides={"tenant_id": "tenant-a"},
        storage_runtime=runtime,
        catalog_path=tmp_path / "catalog.sqlite3",
        control=control,
    )
    asset = writer_cogni.assets.add(source)
    run = writer_cogni.ingest_asset(asset.asset_id)
    document_id = run.results[0].document.document_id

    reader_cogni = Cogni.load(
        context_overrides={"tenant_id": "tenant-b"},
        storage_runtime=runtime,
        catalog_path=tmp_path / "catalog.sqlite3",
        control=control,
    )
    with pytest.raises(IngestAuthorizationError):
        _ = reader_cogni.documents.locate(document_id)
