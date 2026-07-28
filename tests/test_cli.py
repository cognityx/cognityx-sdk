from __future__ import annotations

import json
import os
from pathlib import Path
import time

from cognityx import Cogni
from cognityx.cli import main
from cognityx_storage import StorageConfig, StorageRuntime


def _run(capsys, *arguments: str):
    code = main(list(arguments))
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out else None
    return code, payload, captured.err


def _common(root: Path, catalog: Path) -> tuple[str, ...]:
    return (
        "--tenant-id", "acme",
        "--storage-root", str(root),
        "--catalog-path", str(catalog),
    )


def test_complete_cli_asset_bundle_and_cleanup_lifecycle(
    tmp_path: Path, capsys,
) -> None:
    root, catalog = tmp_path / "storage", tmp_path / "catalog.sqlite3"
    source = tmp_path / "paper.txt"
    source.write_bytes(b"paper")
    common = _common(root, catalog)

    code, bundle, error = _run(
        capsys, "doc-bundles", "create", "phd/rag", *common
    )
    assert code == 0 and error == ""
    bundle_id = bundle["bundle_id"]

    code, created, _ = _run(
        capsys, "assets", "add", str(source), "--bundle", "phd/rag", *common
    )
    assert code == 0
    asset_id = created["asset_id"]
    assert _run(capsys, "assets", "list", "--bundle", "phd/rag", *common)[1][0]["asset_id"] == asset_id
    assert _run(capsys, "assets", "show", asset_id, *common)[1]["asset_id"] == asset_id
    location = _run(capsys, "assets", "locate", asset_id, *common)[1]
    assert Path(location["local_path"]).is_file()
    assert _run(capsys, "doc-bundles", "list", *common)[0] == 0
    assert _run(capsys, "doc-bundles", "locate", bundle_id, *common)[1]["bundle_id"] == bundle_id

    code, _, error = _run(capsys, "assets", "delete", asset_id, *common)
    assert code == 2 and "--yes" in error
    code, deleted, _ = _run(
        capsys, "assets", "delete", asset_id, "--yes", "--reason", "obsolete", *common
    )
    assert code == 0 and deleted["status"] == "deleted"
    assert _run(capsys, "assets", "show", asset_id, *common)[0] == 3
    assert _run(capsys, "assets", "deleted", *common)[1][0]["asset_id"] == asset_id

    dry = _run(capsys, "cleanup", "blobs", "--dry-run", "--older-than", "1h", *common)[1]
    assert dry["dry_run"] is True
    os.utime(location["local_path"], (time.time() - 7200, time.time() - 7200))
    executed = _run(
        capsys, "cleanup", "blobs", "--older-than", "1h", "--yes",
        "--batch-size", "1", *common
    )[1]
    assert executed["dry_run"] is False
    assert executed["result"]["deleted_objects"] == 1

    restored = _run(
        capsys, "assets", "add", str(source), "--bundle", "phd/rag", *common
    )[1]
    assert restored["asset_id"] == asset_id
    assert restored["status"] == "restored"

    code, _, error = _run(
        capsys, "doc-bundles", "delete", bundle_id, "--yes", *common
    )
    assert code == 2 and "not empty" in error
    first = _run(
        capsys, "doc-bundles", "delete", bundle_id, "--recursive", "--yes", *common
    )[1]
    repeated = _run(
        capsys, "doc-bundles", "delete", bundle_id, "--recursive", "--yes", *common
    )[1]
    assert first["status"] == "deleted"
    assert repeated["status"] == "already_deleted"
    assert repeated["deleted_asset_count"] == 0
    assert repeated["deleted_bundle_count"] == 0
    assert _run(capsys, "doc-bundles", "deleted", *common)[0] == 0

    runtime = StorageRuntime.from_config(StorageConfig.built_in(root=root))
    cogni = Cogni.load(
        context_overrides={"tenant_id": "acme"},
        storage_runtime=runtime,
        catalog_path=catalog,
    )
    restored_again = cogni.assets.add(source, bundle="phd/rag")
    with cogni.assets.open(restored_again.asset_id) as stream:
        assert stream.read() == b"paper"


def test_describe_scope_validation_and_confirmation_output(
    tmp_path: Path, capsys,
) -> None:
    root, catalog = tmp_path / "storage", tmp_path / "catalog.sqlite3"
    common = _common(root, catalog)

    code, described, error = _run(capsys, "describe", *common)
    assert code == 0 and error == ""
    assert described["source_asset_catalog"] is None
    assert not catalog.exists()

    code, described, _ = _run(capsys, "describe", "--assets", *common)
    assert code == 0
    assert described["source_asset_catalog"] is not None
    assert catalog.exists()

    code, _, error = _run(
        capsys, "assets", "list", "--scope", "malformed", *common
    )
    assert code == 2
    assert "KEY=VALUE" in error
