from __future__ import annotations

from pathlib import Path

import pytest

from cognityx import Cogni
from cognityx_ingest import SourceAsset
from cognityx_resource import ResourceContext
from cognityx_storage import StorageConfig, StorageRuntime


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
