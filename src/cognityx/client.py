"""The explicit Cognityx SDK composition root."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any

from cognityx_ingest import SourceAssetRegistry
from cognityx_ingest.control import ControlClient
from cognityx_resource import ExecutionContext, ResourceContext, load_resource_context
from cognityx_storage import StorageRuntime

from cognityx.assets import Assets
from cognityx.doc_bundles import DocBundles


class Cogni:
    """Small, explicit composition layer over Cognityx components."""

    def __init__(
        self,
        *,
        context: ResourceContext,
        storage: StorageRuntime,
        catalog_path: str | Path | None = None,
        control: ControlClient | None = None,
    ) -> None:
        self._context = context
        self._storage = storage
        self._catalog_path = catalog_path
        self._control = control
        self._registry: SourceAssetRegistry | None = None
        self._assets: Assets | None = None
        self._doc_bundles: DocBundles | None = None
        self._lock = RLock()

    @classmethod
    def load(
        cls,
        *,
        context: ResourceContext | None = None,
        context_file: str | Path | None = None,
        context_overrides: Mapping[str, object] | None = None,
        cwd: str | Path | None = None,
        user_context_file: str | Path | None = None,
        storage_runtime: StorageRuntime | None = None,
        storage_config: str | Path | None = None,
        catalog_path: str | Path | None = None,
        control: ControlClient | None = None,
    ) -> "Cogni":
        if context is not None and any(
            value is not None
            for value in (context_file, context_overrides, user_context_file)
        ):
            raise ValueError(
                "context cannot be combined with context_file, "
                "context_overrides, or user_context_file."
            )
        if storage_runtime is not None and storage_config is not None:
            raise ValueError(
                "Pass either storage_runtime or storage_config, not both."
            )
        selected_context = context or load_resource_context(
            context_file=context_file,
            overrides=context_overrides,
            cwd=cwd,
            user_context_file=user_context_file,
        )
        selected_storage = storage_runtime or StorageRuntime.load(
            config_file=storage_config,
            cwd=cwd,
        )
        return cls(
            context=selected_context,
            storage=selected_storage,
            catalog_path=catalog_path,
            control=control,
        )

    @property
    def context(self) -> ResourceContext:
        return self._context

    @property
    def context_id(self) -> str:
        return self._context.context_id

    @property
    def storage(self) -> StorageRuntime:
        return self._storage

    @property
    def assets(self) -> Assets:
        with self._lock:
            if self._assets is None:
                self._assets = Assets(self)
            return self._assets

    @property
    def doc_bundles(self) -> DocBundles:
        with self._lock:
            if self._doc_bundles is None:
                self._doc_bundles = DocBundles(self)
            return self._doc_bundles

    @property
    def source_asset_registry(self) -> SourceAssetRegistry:
        with self._lock:
            if self._registry is None:
                self._registry = SourceAssetRegistry.load(
                    runtime=self._storage,
                    catalog_path=self._catalog_path,
                    control=self._control,
                )
            return self._registry

    def new_execution(self) -> ExecutionContext:
        return ExecutionContext.create(self._context)

    def describe(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "context_id": self.context_id,
            "context_type": self.context.context_type,
            "principal_id": self.context.principal_id,
            "tenant_id": self.context.tenant_id,
            "project_id": self.context.project_id,
            "workspace_id": self.context.workspace_id,
            "storage": self._storage.describe(),
            "source_asset_catalog": None,
        }
        with self._lock:
            if self._registry is not None:
                result["source_asset_catalog"] = self._registry.catalog_info()
        return result
