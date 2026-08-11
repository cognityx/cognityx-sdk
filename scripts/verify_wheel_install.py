#!/usr/bin/env python3
"""Verify that the built Cognityx wheel installs and runs independently."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
from zipfile import ZipFile

VERSION = "0.2.0"
EXPECTED = {
    "cognityx-resource": "b23220b69fcb182e681cf13276c37474666c9bd2",
    "cognityx-storage": "4b47b898b2fb465263d8c44350d4241f52b13c90",
    "cognityx-ingest": "56716dbdebde9bd92069cbd415aa7f657d55d9dd",
    "cognityx-jobs": "e4312fd461df97ffcefc54352b9b76f1dd6e6860",
    "cognityx-experiments": "1da25539bcbac165fc5a04f23a78993616b84ea6",
}


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=cwd, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _metadata(wheel: Path) -> str:
    with ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise RuntimeError(f"Expected one METADATA file in {wheel}, found {names}.")
        return archive.read(names[0]).decode()


def _verify_requires_dist(metadata: str) -> None:
    for distribution, sha in EXPECTED.items():
        expected = (
            f"Requires-Dist: {distribution} @ "
            f"git+https://github.com/cognityx/{distribution}.git@{sha}"
        )
        if expected not in metadata:
            raise RuntimeError(f"Wheel metadata is missing exact dependency: {expected}")
    rich_lines = [
        line
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist: cognityx-ingest[")
        and "extra == 'rich-ingest'" in line
    ]
    if len(rich_lines) != 1:
        raise RuntimeError("Wheel metadata is missing the rich-ingest dependency.")
    rich = rich_lines[0]
    if not all(
        expected in rich
        for expected in (
            "docling",
            "pymupdf",
            EXPECTED["cognityx-ingest"],
        )
    ):
        raise RuntimeError(f"Unexpected rich-ingest dependency metadata: {rich}")


def _python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _command(environment: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    directory = "Scripts" if sys.platform == "win32" else "bin"
    return environment / directory / f"{name}{suffix}"


def _verify_installed_references(python: Path) -> None:
    code = """
import importlib.metadata
import json

expected = json.loads(%r)
assert importlib.metadata.version("cognityx") == %r
for name, sha in expected.items():
    distribution = importlib.metadata.distribution(name)
    direct_url = json.loads(distribution.read_text("direct_url.json"))
    assert direct_url["vcs_info"]["commit_id"] == sha, (name, direct_url)
""" % (json.dumps(EXPECTED), VERSION)
    _run([str(python), "-c", code])


def _json(command: list[str]) -> object:
    return json.loads(_run(command).stdout)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="cognityx-wheel-verify-") as temp:
        root = Path(temp)
        dist = root / "dist"
        _run(["uv", "build", "--out-dir", str(dist)], cwd=repository)
        wheels = list(dist.glob("cognityx-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected one Cognityx wheel, found {wheels}.")
        wheel = wheels[0]
        _verify_requires_dist(_metadata(wheel))

        environment = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _python(environment)
        _run([str(python), "-m", "pip", "install", str(wheel)])
        _verify_installed_references(python)

        cogni = _command(environment, "cogni")
        _run([str(cogni), "--help"])
        _run([str(python), "-m", "cognityx", "--help"])

        storage = root / "storage"
        catalog = root / "catalog.sqlite3"
        source = root / "source.txt"
        source.write_bytes(b"installed wheel lifecycle")
        common = [
            "--tenant-id", "wheel-verification",
            "--storage-root", str(storage),
            "--catalog-path", str(catalog),
        ]
        described = _json([str(cogni), "describe", *common])
        if described["source_asset_catalog"] is not None:
            raise RuntimeError("Plain describe unexpectedly initialized the catalog.")
        created = _json([str(cogni), "assets", "add", str(source), *common])
        asset_id = created["asset_id"]
        folder = root / "contracts"
        (folder / "india").mkdir(parents=True)
        (folder / "policy.txt").write_bytes(b"policy")
        (folder / "india" / "agreement.txt").write_bytes(b"agreement")
        batch = _json(
            [
                str(cogni),
                "assets",
                "add",
                str(folder),
                "--bundle",
                "legal",
                "--structure",
                "preserve",
                *common,
            ]
        )
        if batch["created_count"] != 2 or {
            item["bundle_path"] for item in batch["items"]
        } != {"legal", "legal/india"}:
            raise RuntimeError(f"Folder registration mismatch: {batch}")
        deleted = _json([str(cogni), "assets", "delete", asset_id, "--yes", *common])
        if deleted["status"] != "deleted":
            raise RuntimeError(f"Unexpected deletion result: {deleted}")
        deleted_items = _json([str(cogni), "assets", "deleted", *common])
        if [item["asset_id"] for item in deleted_items] != [asset_id]:
            raise RuntimeError(f"Deleted Asset listing mismatch: {deleted_items}")
        plan = _json([str(cogni), "cleanup", "blobs", "--dry-run", *common])
        if plan["dry_run"] is not True:
            raise RuntimeError(f"Cleanup was not a dry run: {plan}")

    print("Cognityx wheel verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
