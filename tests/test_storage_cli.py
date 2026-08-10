from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cognityx.cli import main
from cognityx_storage import StorageLocation, StorageRuntime


def _write_storage_config(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "storage"
    config = tmp_path / "storage.toml"
    config.write_text(
        "\n".join(
            [
                "[storage]",
                'default_profile = "local-main"',
                "",
                "[storage.profiles.local-main]",
                'type = "filesystem"',
                f'root = "{root}"',
                "",
                "[storage.roles.artifact]",
                'profile = "local-main"',
                'namespace = "artifacts"',
            ]
        ),
        encoding="utf-8",
    )
    return root, config


def _run(capsys, *arguments: str):
    code = main(list(arguments))
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out else None
    return code, payload, captured


def test_storage_locate_reports_existing_local_object(
    tmp_path: Path, capsys
) -> None:
    root, config = _write_storage_config(tmp_path)
    runtime = StorageRuntime.load(config_file=config)
    stored = runtime.for_role("artifact").put_bytes(
        "models/adapters/adapter-1/1/adapter-manifest.json",
        b'{"version": 1}',
    )

    code, payload, captured = _run(
        capsys,
        "storage",
        "locate",
        stored.uri,
        "--storage-config",
        str(config),
    )

    assert code == 0
    assert captured.err == ""
    assert payload == {
        "backend": "LocalStorageBackend",
        "exists": True,
        "local_path": str(
            root
            / "artifacts/models/adapters/adapter-1/1/adapter-manifest.json"
        ),
        "profile_name": "local-main",
        "role": "artifact",
        "role_name": "artifact",
        "size_bytes": stored.size_bytes,
        "uri": stored.uri,
    }


def test_storage_locate_reports_missing_local_object_as_success(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "storage"
    uri = "storage://local-main/artifacts/models/missing.json"

    with pytest.warns(FutureWarning, match="--storage-root is deprecated"):
        code, payload, captured = _run(
            capsys,
            "storage",
            "locate",
            uri,
            "--storage-root",
            str(root),
        )

    assert code == 0
    assert captured.err == ""
    assert payload == {
        "backend": "LocalStorageBackend",
        "exists": False,
        "local_path": None,
        "profile_name": "local-main",
        "role": "artifact",
        "role_name": "artifact",
        "size_bytes": None,
        "uri": uri,
    }


def test_storage_locate_rejects_malformed_uri_and_unknown_profile(
    tmp_path: Path, capsys
) -> None:
    _, config = _write_storage_config(tmp_path)

    malformed_code, malformed_payload, malformed = _run(
        capsys,
        "storage",
        "locate",
        "not-a-storage-uri",
        "--storage-config",
        str(config),
    )
    unknown_code, unknown_payload, unknown = _run(
        capsys,
        "storage",
        "locate",
        "storage://unknown/artifacts/report.json",
        "--storage-config",
        str(config),
    )

    assert malformed_code == 2
    assert malformed_payload is None
    assert "storage://<profile>/<logical-key>" in malformed.err
    assert unknown_code == 3
    assert unknown_payload is None
    assert "Storage profile is not configured: unknown" in unknown.err


def test_storage_locate_delegates_to_storage_runtime(
    monkeypatch, capsys
) -> None:
    location = StorageLocation(
        uri="storage://remote-main/artifacts/report.json",
        backend_name="RemoteBackend",
        profile_name="remote-main",
        role_name="artifact",
        local_path=None,
        exists=True,
        size_bytes=17,
    )
    calls: list[str] = []

    class SentinelStorage:
        def locate(self, uri: str) -> StorageLocation:
            calls.append(uri)
            return location

    monkeypatch.setattr(
        "cognityx.cli._load",
        lambda args: SimpleNamespace(storage=SentinelStorage()),
    )

    code = main(["storage", "locate", "opaque-uri-owned-by-storage", "--debug"])
    captured = capsys.readouterr()

    assert code == 0
    assert calls == ["opaque-uri-owned-by-storage"]
    assert captured.err == ""
    assert captured.out == """{
  "backend": "RemoteBackend",
  "exists": true,
  "local_path": null,
  "profile_name": "remote-main",
  "role": "artifact",
  "role_name": "artifact",
  "size_bytes": 17,
  "uri": "storage://remote-main/artifacts/report.json"
}
"""


def test_existing_describe_command_remains_available(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "storage"

    code, payload, _ = _run(
        capsys,
        "describe",
        "--storage-root",
        str(root),
    )

    assert code == 0
    assert payload["storage"]["default_profile"] == "local-main"
