"""Reference-safe SourceAsset Blob cleanup exposed by the SDK."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from cognityx_storage import BlobGcPlan, BlobGcResult

if TYPE_CHECKING:
    from cognityx.client import Cogni


class Cleanup:
    """Thin delegation facade for SourceAssetCleanupService."""

    def __init__(self, owner: "Cogni") -> None:
        self._owner = owner

    def plan_blobs(
        self, *, older_than: timedelta = timedelta(days=7)
    ) -> BlobGcPlan:
        return self._owner.source_asset_cleanup_service.plan_blobs(
            self._owner.new_execution(), older_than=older_than
        )

    def execute_blobs(
        self, plan: BlobGcPlan, *, batch_size: int = 100
    ) -> BlobGcResult:
        return self._owner.source_asset_cleanup_service.execute_blobs(
            self._owner.new_execution(), plan, batch_size=batch_size
        )
