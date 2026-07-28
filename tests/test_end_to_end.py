from __future__ import annotations

from datetime import timedelta
import os
from pathlib import Path
import time

import pytest

from cognityx import Cogni
from cognityx_ingest import SourceAsset
from cognityx_resource import ResourceContext
from cognityx_storage import BlobGcPlan, BlobGcResult, StorageConfig, StorageRuntime


@pytest.mark.parametrize(
    "filename,content",
    [
        ("sample.pdf", b"%PDF-test"),
        ("image.png", b"png"),
        ("audio.mp3", b"mp3"),
        ("video.mp4", b"mp4"),
        ("data.csv", b"a,b\n1,2\n"),
        ("archive.zip", b"PK-test"),
    ],
)
def test_sdk_registers_any_digital_source_asset(
    tmp_path: Path, filename: str, content: bytes
) -> None:
    source = tmp_path / filename
    source.write_bytes(content)
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme"),
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    result = cogni.assets.add(source, bundle="multiformat")
    asset = cogni.assets.get(result.asset_id)
    with cogni.assets.open(asset.asset_id) as stream:
        reopened = stream.read()

    assert isinstance(asset, SourceAsset)
    assert asset.original_filename == filename
    assert asset.size_bytes == len(content)
    assert reopened == content


def test_sdk_complete_asset_lifecycle_restores_after_cleanup(
    tmp_path: Path,
) -> None:
    source = tmp_path / "restore.txt"
    source.write_bytes(b"restore through sdk")
    runtime = StorageRuntime.from_config(
        StorageConfig.built_in(root=tmp_path / "storage")
    )
    cogni = Cogni.load(
        context=ResourceContext(tenant_id="acme"),
        storage_runtime=runtime,
        catalog_path=tmp_path / "catalog.sqlite3",
    )
    created = cogni.assets.add(source)
    location = cogni.assets.locate(created.asset_id)

    cogni.assets.delete(created.asset_id)
    old = time.time() - 10
    os.utime(location.local_path, (old, old))
    plan = cogni.cleanup.plan_blobs(older_than=timedelta(seconds=1))

    assert isinstance(plan, BlobGcPlan)
    assert len(plan.deletion_candidates) == 1
    assert Path(location.local_path).exists()

    result = cogni.cleanup.execute_blobs(plan, batch_size=1)
    restored = cogni.assets.add(source)

    assert isinstance(result, BlobGcResult)
    assert result.deleted_objects == 1
    assert restored.status == "restored"
    assert restored.asset_id == created.asset_id
    with cogni.assets.open(restored.asset_id) as stream:
        assert stream.read() == b"restore through sdk"
