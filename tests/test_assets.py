from __future__ import annotations

from pathlib import Path

from cognityx import Cogni
from cognityx_ingest import (
    SourceAsset,
    SourceAssetBatchResult,
    SourceAssetDeletionResult,
    SourceAssetRegistrationResult,
)
from cognityx_resource import ResourceContext
from cognityx_storage import StorageConfig, StorageRuntime


class RecordingControl:
    def __init__(self) -> None:
        self.contexts = []

    def authorize(self, context, action, resource=None, request=None):
        self.contexts.append(context)
        from cognityx_ingest.control import ControlDecision

        return ControlDecision(allowed=True)

    def report_usage(self, context, usage) -> None:
        return None


def test_assets_facade_delegates_and_creates_fresh_executions(tmp_path: Path) -> None:
    source = tmp_path / "interview.mp3"
    source.write_bytes(b"audio")
    control = RecordingControl()
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme", principal_id="alice"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
        control=control,
    )

    result = cogni.assets.add(source, bundle="research/interviews")
    listed = cogni.assets.list(bundle="research/interviews")
    asset = cogni.assets.get(result.asset_id)
    with cogni.assets.open(asset.asset_id) as stream:
        content = stream.read()
    location = cogni.assets.locate(asset.asset_id)

    assert isinstance(result, SourceAssetRegistrationResult)
    assert isinstance(asset, SourceAsset)
    assert asset.ref.resource_id == asset.asset_id
    assert listed == (asset,)
    assert content == b"audio"
    assert location.asset_id == asset.asset_id
    assert len(control.contexts) >= 4
    assert len({item.context_id for item in control.contexts}) == 1
    # One facade action may authorize several component operations, but each
    # facade action starts with a fresh execution identity.
    assert len({item.run_id for item in control.contexts}) >= 4
    assert len({item.correlation_id for item in control.contexts}) >= 4


def test_assets_lifecycle_returns_canonical_models(tmp_path: Path) -> None:
    source = tmp_path / "asset.txt"
    source.write_bytes(b"asset")
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )
    created = cogni.assets.add(source)

    deleted = cogni.assets.delete(created.asset_id, reason="superseded")

    assert isinstance(deleted, SourceAssetDeletionResult)
    assert deleted.status == "deleted"
    assert cogni.assets.list_deleted()[0].asset_id == created.asset_id
    for operation in (
        lambda: cogni.assets.get(created.asset_id),
        lambda: cogni.assets.open(created.asset_id),
        lambda: cogni.assets.locate(created.asset_id),
    ):
        import pytest

        with pytest.raises(KeyError):
            operation()


def test_assets_directory_add_delegates_one_execution_for_complete_batch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "contracts"
    (source / "india").mkdir(parents=True)
    (source / "policy.txt").write_bytes(b"policy")
    (source / "india/agreement.txt").write_bytes(b"agreement")
    control = RecordingControl()
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme", principal_id="alice"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
        control=control,
    )

    result = cogni.assets.add(
        source,
        bundle="legal",
        structure="preserve",
        recursive=True,
    )

    assert isinstance(result, SourceAssetBatchResult)
    assert result.created_count == 2
    assert {item.bundle_path for item in result.items} == {
        "legal",
        "legal/india",
    }
    assert len({item.run_id for item in control.contexts}) == 1
    assert len({item.correlation_id for item in control.contexts}) == 1
