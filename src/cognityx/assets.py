"""Canonical SourceAsset operations exposed by the SDK."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from cognityx_ingest.models import (
    SourceAsset,
    SourceAssetBatchResult,
    SourceAssetDeletionResult,
    SourceAssetLocation,
    SourceAssetRegistrationResult,
)

if TYPE_CHECKING:
    from cognityx.client import Cogni


class Assets:
    """Thin delegation facade for SourceAssetRegistry."""

    def __init__(self, owner: "Cogni") -> None:
        self._owner = owner

    def add(
        self,
        path: str | Path,
        *,
        bundle: str | None = None,
        structure: str = "preserve",
        recursive: bool = True,
    ) -> SourceAssetRegistrationResult | SourceAssetBatchResult:
        execution = self._owner.new_execution()
        return self._owner.source_asset_registry.register_path(
            execution,
            path,
            bundle=bundle,
            structure=structure,
            recursive=recursive,
        )

    def list(self, *, bundle: str | None = None) -> tuple[SourceAsset, ...]:
        return self._owner.source_asset_registry.list_assets(
            self._owner.new_execution(), bundle=bundle
        )

    def get(self, asset_id: str) -> SourceAsset:
        return self._owner.source_asset_registry.show_asset(
            self._owner.new_execution(), asset_id
        )

    def open(self, asset_id: str) -> BinaryIO:
        return self._owner.source_asset_registry.open_asset(
            self._owner.new_execution(), asset_id
        )

    def locate(self, asset_id: str) -> SourceAssetLocation:
        return self._owner.source_asset_registry.locate_asset(
            self._owner.new_execution(), asset_id
        )

    def delete(
        self, asset_id: str, *, reason: str | None = None
    ) -> SourceAssetDeletionResult:
        return self._owner.source_asset_registry.delete_asset(
            self._owner.new_execution(), asset_id, reason=reason
        )

    def list_deleted(self) -> tuple[SourceAsset, ...]:
        return self._owner.source_asset_registry.list_deleted_assets(
            self._owner.new_execution()
        )
