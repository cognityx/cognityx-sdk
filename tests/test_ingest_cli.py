from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from pypdf import PdfWriter

from cognityx.cli import main


def _run(capsys, *arguments: str):
    code = main(list(arguments))
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out else None
    return code, payload, captured.err


def _configure_runtime(tmp_path: Path, monkeypatch) -> Path:
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
                "[storage.roles.source_asset]",
                'profile = "local-main"',
                'namespace = "source-assets"',
                'dedup_scope = "tenant"',
                "",
                "[storage.roles.artifact]",
                'profile = "local-main"',
                'namespace = "artifacts"',
                "",
                "[storage.roles.catalog]",
                'profile = "local-main"',
                'namespace = "catalog"',
                'preferred_capabilities = ["native_path", "random_write", "file_locking"]',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("COGNITYX_STORAGE_CONFIG", str(config))
    return root


def _write_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as stream:
        writer.write(stream)


def _write_configured_pdf(path: Path) -> None:
    if importlib.util.find_spec("fitz") is None:
        _write_pdf(path)
        return
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "1. Configuration-first ingest")
    page.insert_text((72, 96), "A small document for parser integration.")
    document.save(path)
    document.close()


def test_cogni_complete_dataforge_ingest_flow(tmp_path: Path, monkeypatch, capsys) -> None:
    root = _configure_runtime(tmp_path, monkeypatch)
    source = tmp_path / "paper.pdf"
    _write_pdf(source)

    code, first, error = _run(
        capsys, "assets", "add", str(source), "--bundle", "research"
    )
    assert code == 0 and error == ""
    asset_id = first["asset_id"]

    code, repeated, _ = _run(
        capsys, "assets", "add", str(source), "--bundle", "research"
    )
    assert code == 0
    assert repeated["asset_id"] == asset_id
    assert repeated["status"] == "already_registered"
    blobs = tuple(
        path
        for path in (root / "source-assets" / "blob-domains").rglob("*")
        if path.is_file()
    )
    assert len(blobs) == 1

    bundles = _run(capsys, "doc-bundles", "list")[1]
    bundle_id = next(item["bundle_id"] for item in bundles if item["path"] == "research")

    path_run = _run(capsys, "ingest", str(source))[1]
    asset_run = _run(capsys, "ingest", "--asset", asset_id)[1]
    bundle_run = _run(capsys, "ingest", "--bundle-id", bundle_id)[1]

    assert path_run["document_count"] == 1
    assert asset_run["documents"][0]["asset_id"] == asset_id
    assert bundle_run["root_bundle_id"] == bundle_id
    assert all(item["run_id"] and item["job_id"] for item in (path_run, asset_run, bundle_run))

    status = _run(capsys, "jobs", "status", bundle_run["job_id"])[1]
    events = _run(capsys, "jobs", "events", bundle_run["job_id"])[1]
    assert status["job"]["state"] == "completed"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["event"] == "run_completed"

    document_id = bundle_run["documents"][0]["document_id"]
    run_record = _run(capsys, "runs", "show", bundle_run["run_id"])[1]
    evidence_payload = _run(capsys, "artifacts", "read", document_id, "evidence")[1]
    evidence = json.loads(evidence_payload["content"].splitlines()[0])

    assert run_record["schema_version"] == "cognityx.ingest.run/v2"
    assert run_record["document_ids"] == [document_id]
    assert evidence["schema_version"] == "cognityx.ingest.evidence/v2"
    assert evidence["source_asset_id"] == asset_id
    assert evidence["bundle_id"] == bundle_id
    assert evidence["run_id"] == bundle_run["run_id"]
    assert evidence["page_number"] == 1

    assert main(["jobs", "watch", bundle_run["job_id"]]) == 0
    watched = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert watched[-1]["event"] == "run_completed"


def test_singular_bundle_path_and_provenance_flow(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _configure_runtime(tmp_path, monkeypatch)
    source = tmp_path / "policy.pdf"
    _write_pdf(source)

    first = _run(
        capsys,
        "bundle",
        "create",
        "legal/hr",
        "--tenant-id",
        "tenant-a",
    )[1]
    second = _run(
        capsys,
        "bundle",
        "create",
        "legal/hr",
        "--tenant-id",
        "tenant-b",
    )[1]
    assert first["path"] == second["path"] == "legal/hr"
    assert first["context_id"] != second["context_id"]
    assert first["bundle_id"] != second["bundle_id"]

    asset = _run(
        capsys,
        "asset",
        "add",
        str(source),
        "--bundle",
        "legal/hr",
        "--tenant-id",
        "tenant-a",
    )[1]
    run = _run(
        capsys,
        "ingest",
        "--bundle",
        "legal/hr",
        "--tenant-id",
        "tenant-a",
    )[1]
    assert run["root_bundle_id"] == first["bundle_id"]
    assert run["documents"][0]["asset_id"] == asset["asset_id"]

    status = _run(
        capsys,
        "job",
        "status",
        run["job_id"],
        "--tenant-id",
        "tenant-a",
    )[1]
    document_id = run["documents"][0]["document_id"]
    provenance = _run(
        capsys,
        "artifact",
        "read",
        document_id,
        "provenance",
        "--tenant-id",
        "tenant-a",
    )[1]
    payload = json.loads(provenance["content"])

    assert status["job"]["state"] == "completed"
    assert payload["source_asset"]["asset_id"] == asset["asset_id"]
    assert payload["pages"][0]["physical_page_index"] == 0
    assert payload["parser"]["selected"] == "basic"


def test_plain_ingest_uses_project_parser_configuration_and_provenance_v2(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _configure_runtime(tmp_path, monkeypatch)
    config = tmp_path / ".cognityx" / "ingest.toml"
    config.parent.mkdir()
    config.write_text(
        "\n".join(
            (
                "[ingest]",
                'parser_policy = "compare"',
                'parser_backends = ["pymupdf", "docling", "basic"]',
                "",
                "[ingest.inference]",
                "enabled = false",
            )
        ),
        encoding="utf-8",
    )
    source = tmp_path / "configured.pdf"
    _write_configured_pdf(source)
    monkeypatch.chdir(tmp_path)

    run = _run(capsys, "ingest", str(source))[1]
    document_id = run["documents"][0]["document_id"]
    provenance = _run(
        capsys, "artifact", "read", document_id, "provenance"
    )[1]
    payload = json.loads(provenance["content"])

    assert payload["schema_version"] == "cognityx.ingest.provenance/v2"
    assert payload["parser"]["selected"] == "fusion"
    assert set(payload["parser"]["considered"]) == {
        "pymupdf",
        "docling",
        "basic",
    }
    source_backends = set(payload["parser"]["diagnostics"]["source_backends"])
    assert "basic" in source_backends
    if importlib.util.find_spec("fitz") is not None:
        assert "pymupdf" in source_backends
    assert source_backends <= set(payload["parser"]["considered"])


def test_storage_root_remains_compatible_with_warning(tmp_path: Path, capsys) -> None:
    source = tmp_path / "asset.txt"
    source.write_text("asset", encoding="utf-8")

    import pytest

    with pytest.warns(FutureWarning, match="--storage-root is deprecated"):
        code = main(
            ["assets", "add", str(source), "--storage-root", str(tmp_path / "storage")]
        )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["asset_id"].startswith("src-")
