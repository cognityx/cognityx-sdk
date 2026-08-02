"""Run-level artifact inspection helpers exposed by the SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cognityx.client import Cogni


class Runs:
    """Locate all generated artifacts for one ingest run."""

    def __init__(self, owner: "Cogni") -> None:
        self._owner = owner

    def locate(self, run_id: str) -> dict[str, object]:
        manifest = self._owner.ingest_manager.show_run(self._owner.new_execution(), run_id)
        artifact_uris: dict[str, str] = {}
        for index, uri in enumerate(manifest.get("document_manifest_refs", ())):
            artifact_uris[f"document_manifest[{index}]"] = uri
        for index, uri in enumerate(manifest.get("evidence_refs", ())):
            artifact_uris[f"evidence[{index}]"] = uri
        for index, uri in enumerate(manifest.get("provenance_refs", ())):
            artifact_uris[f"provenance[{index}]"] = uri
        run_manifest_uri = manifest.get("run_manifest_uri")
        if run_manifest_uri is not None:
            artifact_uris["run_manifest"] = run_manifest_uri

        return {
            "run_id": run_id,
            "artifacts": {
                key: self._owner.storage.locate(uri).to_dict()
                for key, uri in artifact_uris.items()
            },
        }
