from __future__ import annotations

from pathlib import Path

from cognityx import Cogni
from cognityx_ingest import DocBundle
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
