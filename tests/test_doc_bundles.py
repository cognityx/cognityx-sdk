from __future__ import annotations

from pathlib import Path

from cognityx import Cogni
import pytest

from cognityx_ingest import DocBundle, DocBundleDeletionResult
from cognityx_resource import ResourceContext
from cognityx_storage import StorageConfig, StorageRuntime


def test_doc_bundle_facade_uses_same_registry(tmp_path: Path) -> None:
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    bundle = cogni.doc_bundles.create("research/interviews")
    bundles = cogni.doc_bundles.list()
    location = cogni.doc_bundles.locate(bundle.bundle_id)

    assert isinstance(bundle, DocBundle)
    assert bundle in bundles
    assert len(bundles) == 2
    assert location["bundle_id"] == bundle.bundle_id
    assert cogni.assets._owner.source_asset_registry is cogni.doc_bundles._owner.source_asset_registry


def test_doc_bundle_lifecycle_preserves_recursive_rule_and_counts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "nested.txt"
    source.write_bytes(b"nested")
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )
    bundle = cogni.doc_bundles.create("parent/child")
    cogni.assets.add(source, bundle="parent/child")

    with pytest.raises(ValueError, match="not empty"):
        cogni.doc_bundles.delete(bundle.bundle_id)
    first = cogni.doc_bundles.delete(bundle.bundle_id, recursive=True)
    repeated = cogni.doc_bundles.delete(bundle.bundle_id, recursive=True)

    assert isinstance(first, DocBundleDeletionResult)
    assert first.status == "deleted"
    assert first.deleted_asset_count == 1
    assert first.deleted_bundle_count == 1
    assert repeated.status == "already_deleted"
    assert repeated.deleted_asset_count == 0
    assert repeated.deleted_bundle_count == 0
    assert cogni.doc_bundles.list_deleted()[0].bundle_id == bundle.bundle_id
