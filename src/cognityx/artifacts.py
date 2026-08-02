"""Artifact inspection helpers exposed by the SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cognityx.client import Cogni


class Artifacts:
    """Locate one generated ingest artifact by URI resolution."""

    def __init__(self, owner: "Cogni") -> None:
        self._owner = owner

    def locate(self, document_id: str, name: str) -> dict[str, object]:
        document = self._owner.ingest_manager.show_document(
            self._owner.new_execution(), document_id
        )
        artifacts = document["manifest"]["artifacts"]

        try:
            storage_uri = artifacts[name]["uri"]
        except KeyError as error:
            available = ", ".join(sorted(artifacts))
            raise ValueError(
                f"Cannot locate unknown artifact {name!r}; choose one of: {available}."
            ) from error

        return {
            "document_id": document_id,
            "name": name,
            "location": self._owner.storage.locate(storage_uri).to_dict(),
        }
