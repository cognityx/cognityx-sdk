"""Document-level artifact inspection helpers exposed by the SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cognityx.client import Cogni


class Documents:
    """Locate all generated artifacts for one ingest document."""

    def __init__(self, owner: "Cogni") -> None:
        self._owner = owner

    def locate(self, document_id: str) -> dict[str, object]:
        manifest = self._owner.ingest_manager.show_document(
            self._owner.new_execution(), document_id
        )["manifest"]
        artifact_uris: dict[str, str] = {
            key: item["uri"] for key, item in manifest["artifacts"].items()
        }

        return {
            "document_id": document_id,
            "artifacts": {
                key: self._owner.storage.locate(uri).to_dict()
                for key, uri in artifact_uris.items()
            },
        }
