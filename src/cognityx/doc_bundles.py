"""Canonical DocBundle operations exposed by the SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cognityx_ingest.models import DocBundle, DocBundleDeletionResult

if TYPE_CHECKING:
    from cognityx.client import Cogni


class DocBundles:
    """Thin delegation facade for SourceAssetRegistry DocBundle methods."""

    def __init__(self, owner: "Cogni") -> None:
        self._owner = owner

    def create(self, path: str) -> DocBundle:
        return self._owner.source_asset_registry.resolve_doc_bundle(
            self._owner.new_execution(), path, create=True
        )

    def list(self) -> tuple[DocBundle, ...]:
        return self._owner.source_asset_registry.list_doc_bundles(
            self._owner.new_execution()
        )

    def locate(self, bundle_id: str) -> dict[str, str | None]:
        return self._owner.source_asset_registry.locate_doc_bundle(
            self._owner.new_execution(), bundle_id
        )

    def resolve(self, path: str, *, create: bool = False) -> DocBundle:
        return self._owner.source_asset_registry.resolve_doc_bundle(
            self._owner.new_execution(), path, create=create
        )

    def delete(
        self,
        bundle_id: str,
        *,
        recursive: bool = False,
        reason: str | None = None,
    ) -> DocBundleDeletionResult:
        return self._owner.source_asset_registry.delete_doc_bundle(
            self._owner.new_execution(),
            bundle_id,
            recursive=recursive,
            reason=reason,
        )

    def list_deleted(self) -> tuple[DocBundle, ...]:
        return self._owner.source_asset_registry.list_deleted_doc_bundles(
            self._owner.new_execution()
        )
