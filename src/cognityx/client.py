"""The explicit Cognityx SDK composition root."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any

from cognityx_ingest import (
    BoundedInferenceResolver,
    ExtractionPolicy,
    IngestManager,
    IngestRunResult,
    IngestService,
    ParserRouter,
    SourceAssetCleanupService,
    SourceAssetRegistry,
)
from cognityx_ingest.enhancement import load_resolution_config
from cognityx_ingest.control import ControlClient
from cognityx_jobs import JobRepository
from cognityx_resource import ExecutionContext, ResourceContext, load_resource_context
from cognityx_storage import StorageRuntime

from cognityx.assets import Assets
from cognityx.cleanup import Cleanup
from cognityx.doc_bundles import DocBundles
from cognityx.ingest_config import IngestConfiguration, load_ingest_configuration


class Cogni:
    """Small, explicit composition layer over Cognityx components."""

    def __init__(
        self,
        *,
        context: ResourceContext,
        storage: StorageRuntime,
        catalog_path: str | Path | None = None,
        jobs_database: str | Path | None = None,
        inference_config: str | Path | None = None,
        parser_policy: str = "fixed",
        parser_backends: tuple[str, ...] = ("basic",),
        inference_enabled: bool | None = None,
        ingest_configuration: IngestConfiguration | None = None,
        control: ControlClient | None = None,
    ) -> None:
        self._context = context
        self._storage = storage
        self._catalog_path = catalog_path
        self._jobs_database = Path(jobs_database) if jobs_database else None
        self._inference_config = Path(inference_config) if inference_config else None
        self._ingest_configuration = ingest_configuration or IngestConfiguration(
            parser_policy=parser_policy,
            parser_backends=parser_backends,
            inference_enabled=(
                bool(inference_config)
                if inference_enabled is None
                else inference_enabled
            ),
            sources={
                "parser_policy": "constructor",
                "parser_backends": "constructor",
                "inference_enabled": "constructor",
            },
        )
        self._parser_policy = self._ingest_configuration.parser_policy
        self._parser_backends = self._ingest_configuration.parser_backends
        self._inference_enabled = self._ingest_configuration.inference_enabled
        self._control = control
        self._registry: SourceAssetRegistry | None = None
        self._assets: Assets | None = None
        self._doc_bundles: DocBundles | None = None
        self._cleanup_service: SourceAssetCleanupService | None = None
        self._cleanup: Cleanup | None = None
        self._jobs: JobRepository | None = None
        self._ingest_service: IngestService | None = None
        self._ingest_manager: IngestManager | None = None
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
        jobs_database: str | Path | None = None,
        inference_config: str | Path | None = None,
        parser_policy: str | None = None,
        parser_backends: tuple[str, ...] | None = None,
        inference_enabled: bool | None = None,
        user_ingest_config_file: str | Path | None = None,
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
        selected_ingest = load_ingest_configuration(
            cwd=cwd,
            user_config_file=user_ingest_config_file,
            parser_policy=parser_policy,
            parser_backends=parser_backends,
            inference_enabled=(
                True if inference_config is not None else inference_enabled
            ),
        )
        return cls(
            context=selected_context,
            storage=selected_storage,
            catalog_path=catalog_path,
            jobs_database=jobs_database,
            inference_config=inference_config,
            parser_policy=selected_ingest.parser_policy,
            parser_backends=selected_ingest.parser_backends,
            inference_enabled=selected_ingest.inference_enabled,
            ingest_configuration=selected_ingest,
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
    def ingest_configuration(self) -> IngestConfiguration:
        return self._ingest_configuration

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
    def cleanup(self) -> Cleanup:
        with self._lock:
            if self._cleanup is None:
                self._cleanup = Cleanup(self)
            return self._cleanup

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

    @property
    def source_asset_cleanup_service(self) -> SourceAssetCleanupService:
        with self._lock:
            if self._cleanup_service is None:
                self._cleanup_service = SourceAssetCleanupService(
                    registry=self.source_asset_registry,
                    storage_runtime=self._storage,
                    control=self._control,
                )
            return self._cleanup_service

    @property
    def job_repository(self) -> JobRepository:
        with self._lock:
            if self._jobs is None:
                database = self._jobs_database or self._storage.for_role(
                    "catalog"
                ).native_path("ingest/jobs.sqlite3")
                database.parent.mkdir(parents=True, exist_ok=True)
                self._jobs = JobRepository(str(database))
            return self._jobs

    @property
    def ingest_service(self) -> IngestService:
        with self._lock:
            if self._ingest_service is None:
                resolution_config = (
                    load_resolution_config(self._inference_config)
                    if self._inference_enabled
                    else None
                )
                if self._inference_enabled and resolution_config is None:
                    raise ValueError(
                        "Ingest inference is enabled but no inference target "
                        "configuration was supplied."
                    )
                resolver = (
                    BoundedInferenceResolver(resolution_config)
                    if resolution_config is not None
                    else None
                )
                extractor = ParserRouter(
                    policy=ExtractionPolicy(
                        self._parser_policy, self._parser_backends
                    ),
                    selector=resolver if self._parser_policy == "agent" else None,
                )
                self._ingest_service = IngestService(
                    self._storage.for_role("artifact"),
                    extractor=extractor,
                    jobs=self.job_repository,
                    registry=self.source_asset_registry,
                    control=self._control,
                    resolver=resolver,
                )
            return self._ingest_service

    @property
    def ingest_manager(self) -> IngestManager:
        with self._lock:
            if self._ingest_manager is None:
                self._ingest_manager = IngestManager(
                    self._storage.for_role("artifact"),
                    self.job_repository,
                    control=self._control,
                )
            return self._ingest_manager

    def ingest_path(self, path: str | Path) -> IngestRunResult:
        execution = self.new_execution()
        return self.ingest_service.ingest_path(
            path,
            owner_id=execution.principal_id or "local",
            context=execution,
            registry=self.source_asset_registry,
        )

    def ingest_asset(self, asset_id: str) -> IngestRunResult:
        execution = self.new_execution()
        asset = self.source_asset_registry.show_asset(execution, asset_id)
        return self.ingest_service.ingest_assets(
            (asset.asset_id,),
            self.source_asset_registry,
            execution,
            submitted_input={"type": "asset", "asset_id": asset.asset_id},
            root_bundle_id=asset.bundle_id,
        )

    def ingest_bundle(self, bundle_id: str) -> IngestRunResult:
        return self.ingest_service.ingest_bundle(
            bundle_id, self.source_asset_registry, self.new_execution()
        )

    def ingest_bundle_path(self, path: str) -> IngestRunResult:
        bundle = self.doc_bundles.resolve(path, create=False)
        return self.ingest_bundle(bundle.bundle_id)

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
            "ingest": self._ingest_configuration.to_dict()["ingest"],
            "source_asset_catalog": None,
        }
        with self._lock:
            if self._registry is not None:
                result["source_asset_catalog"] = self._registry.catalog_info()
        return result
