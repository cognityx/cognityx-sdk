"""Compose Cognityx components behind one stable, lazy application root.

``Cogni`` exists so applications and the ``cogni`` CLI share one construction
path for Resource context, Storage, Jobs, Ingest, authorization, and optional
bounded inference.  The class delegates domain behavior to component APIs,
initializes expensive services only when first used, and creates a fresh
execution context for each operation.  It does not duplicate parser, persistence,
provenance, or cleanup algorithms owned by those components.
"""

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
from cognityx.artifacts import Artifacts
from cognityx.cleanup import Cleanup
from cognityx.doc_bundles import DocBundles
from cognityx.documents import Documents
from cognityx.ingest_config import IngestConfiguration, load_ingest_configuration
from cognityx.provenance import Provenance
from cognityx.runs import Runs


class Cogni:
    """Provide the primary Python composition root for Cognityx applications.

    Applications normally call ``Cogni.load``; tests and embedded deployments may
    inject already-resolved component objects through the constructor.  Facades
    and services are initialized lazily under one reentrant lock, while each
    action receives a fresh execution identity derived from the stable Resource
    context.  The instance owns no parsing semantics: it wires validated settings
    to merged component APIs and returns their canonical results.
    """

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
        """Store resolved dependencies and prepare lazy component slots.

        ``load`` and advanced dependency-injection callers construct the root with
        one trusted Resource context and Storage runtime.  Existing parser policy,
        backend order, and inference enablement are frozen into one effective
        ``IngestConfiguration``; no parser, model, registry, database, graph, or
        artifact is opened during construction.  Lazy properties synchronize
        first creation with ``RLock`` and then reuse component instances.
        """
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
        self._artifacts: Artifacts | None = None
        self._provenance: Provenance | None = None
        self._documents: Documents | None = None
        self._runs: Runs | None = None
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
        """Resolve local configuration and return one ready, still-lazy root.

        Applications and the CLI use this primary factory.  It rejects conflicting
        injected/discovered context or Storage inputs, resolves Resource, Storage,
        and per-value Ingest configuration in order, then delegates to ``__init__``.
        Local configuration reads are the only immediate side effect; parsers,
        models, catalogs, jobs, and artifacts remain unopened.  Component loaders
        retain their typed failures, and equal inputs produce equivalent wiring.
        """
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
        """Return the stable immutable Resource context shared by all actions.

        Facades and diagnostics read this injected/resolved value; no copy, I/O,
        authorization, or mutation occurs.  Fresh operation identity belongs to
        ``new_execution`` rather than this long-lived governance context.
        """
        return self._context

    @property
    def context_id(self) -> str:
        """Return the canonical identifier of the shared Resource context.

        CLI serializers and component composition use this deterministic shortcut.
        It delegates to the immutable context, performs no I/O, and is safe for
        concurrent reads throughout the ``Cogni`` lifecycle.
        """
        return self._context.context_id

    @property
    def storage(self) -> StorageRuntime:
        """Return the configured public Storage runtime without backend access.

        SDK facades use this runtime to select logical roles and resolve canonical
        URIs.  The property does not initialize or mutate a backend and deliberately
        exposes no private implementation attributes or new ownership semantics.
        """
        return self._storage

    @property
    def ingest_configuration(self) -> IngestConfiguration:
        """Return validated effective Ingest settings and per-value sources.

        Applications and configuration diagnostics inspect this immutable record.
        Reading it performs no parser, model, file, or network operation; execution
        consumes the same values later when ``ingest_service`` is first requested.
        """
        return self._ingest_configuration

    @property
    def assets(self) -> Assets:
        """Return the lazy SourceAsset facade under synchronized first creation.

        Python and CLI asset commands call this property.  It constructs only a
        lightweight owner-bound facade, reuses it thereafter, and does not open the
        catalog or source bytes until a facade method requests them.
        """
        with self._lock:
            if self._assets is None:
                self._assets = Assets(self)
            return self._assets

    @property
    def doc_bundles(self) -> DocBundles:
        """Return the lazy logical bundle facade under the shared lock.

        Bundle commands and ``ingest_bundle_path`` use this stable facade.  First
        access has no Storage or registry side effect beyond allocating the wrapper;
        domain validation and persistence remain in Ingest when methods are called.
        """
        with self._lock:
            if self._doc_bundles is None:
                self._doc_bundles = DocBundles(self)
            return self._doc_bundles

    @property
    def artifacts(self) -> Artifacts:
        """Return the lazy closed settled-artifact inspection facade.

        Python and CLI read/locate commands share this instance.  Construction is
        synchronized and side-effect free; each operation later authorizes afresh,
        verifies immutable manifest URI bindings, and avoids parser initialization.
        """
        with self._lock:
            if self._artifacts is None:
                self._artifacts = Artifacts(self)
            return self._artifacts

    @property
    def provenance(self) -> Provenance:
        """Return the lazy deterministic provenance-address facade.

        Python callers and the ``cogni provenance`` command use this property.
        First access constructs only the lightweight SDK facade under the shared
        reentrant lock; graphs, catalogs, parsers, and inference remain unloaded
        until an explicit resolve call reads authorized settled artifacts.  Later
        accesses return the same stateless facade safely.
        """
        with self._lock:
            if self._provenance is None:
                self._provenance = Provenance(self)
            return self._provenance

    @property
    def documents(self) -> Documents:
        """Return the lazy document-level diagnostic facade.

        Existing document locate callers use this compatibility wrapper.  The
        property allocates it once under ``RLock`` and performs no document read;
        authorization and Storage lookup occur only in explicit facade methods.
        """
        with self._lock:
            if self._documents is None:
                self._documents = Documents(self)
            return self._documents

    @property
    def runs(self) -> Runs:
        """Return the lazy run-level diagnostic facade.

        Existing run locate callers use the same owner-bound object for the root's
        lifetime.  First creation is thread-safe and performs no Jobs or Storage
        I/O; component failures occur only during an explicit run operation.
        """
        with self._lock:
            if self._runs is None:
                self._runs = Runs(self)
            return self._runs

    @property
    def cleanup(self) -> Cleanup:
        """Return the lazy SDK wrapper for reference-safe Blob cleanup.

        Administrative callers use this facade to plan or explicitly execute
        cleanup.  Access alone neither initializes the registry nor deletes data;
        the underlying Ingest/Storage service is requested only by facade methods.
        """
        with self._lock:
            if self._cleanup is None:
                self._cleanup = Cleanup(self)
            return self._cleanup

    @property
    def source_asset_registry(self) -> SourceAssetRegistry:
        """Load once and return the shared Ingest SourceAsset registry.

        Asset, bundle, ingest, and cleanup composition call this advanced property.
        Under ``RLock`` it asks Ingest to load the configured catalog and control
        boundary, then reuses that instance.  Loading may create/open catalog state
        and propagates component failures; no source object is parsed here.
        """
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
        """Return one cleanup service sharing this root's registry and Storage.

        ``Cleanup`` calls this synchronized property when work is requested.  First
        access composes existing Ingest behavior from the shared dependencies; it
        does not itself plan or delete objects.  Reuse prevents split cleanup state.
        """
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
        """Open once and return the durable Jobs repository for Ingest work.

        Ingest service/manager construction calls this property.  It chooses an
        explicit database or the catalog role's canonical native path, creates the
        parent directory when needed, and opens ``JobRepository`` under the lock.
        That filesystem initialization is idempotent; Jobs owns concurrency and
        typed persistence failures after construction.
        """
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
        """Compose the existing executable parser path on first ingest action.

        ``ingest_*`` methods call this synchronized property.  It conditionally
        loads approved bounded-inference configuration, constructs the established
        ``ParserRouter`` from validated legacy policy/backends, and injects shared
        Storage, Jobs, registry, control, and resolver dependencies into Ingest.
        Missing required inference targets fail before parsing.  No adaptive T04
        plan is fabricated, and later accesses reuse the same service.
        """
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
        """Return one authorization-aware manager for generated Ingest state.

        CLI administration and artifact facades call this synchronized property.
        It composes the merged manager with artifact Storage, Jobs, and Control,
        performs no read/delete by itself, and reuses one instance so all callers
        share the same component boundaries and thread-safety assumptions.
        """
        with self._lock:
            if self._ingest_manager is None:
                self._ingest_manager = IngestManager(
                    self._storage.for_role("artifact"),
                    self.job_repository,
                    control=self._control,
                )
            return self._ingest_manager

    def ingest_path(self, path: str | Path) -> IngestRunResult:
        """Ingest one path through the normal registered-source production flow.

        Applications and ``cogni ingest <path>`` call this method.  It creates one
        fresh execution, delegates registration/parsing/persistence to Ingest, and
        returns the canonical run result.  Source, job, and artifact side effects
        are component-owned; typed input/parser/control failures propagate.
        """
        execution = self.new_execution()
        return self.ingest_service.ingest_path(
            path,
            owner_id=execution.principal_id or "local",
            context=execution,
            registry=self.source_asset_registry,
        )

    def ingest_asset(self, asset_id: str) -> IngestRunResult:
        """Ingest one existing SourceAsset under a fresh execution context.

        Python and ``--asset`` callers provide a canonical asset ID.  The method
        authorizes exact registry lookup, delegates one-asset ingestion with stable
        submitted-input metadata, and returns the component result.  It performs no
        fallback asset selection and preserves registry/Ingest typed failures.
        """
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
        """Ingest every eligible SourceAsset in one exact bundle identifier.

        Advanced Python and compatibility CLI callers use this ID-based method.
        It creates a fresh execution and delegates ordering, authorization, job
        lifecycle, parsing, and persistence entirely to Ingest; no SDK traversal or
        parser selection algorithm is introduced.
        """
        return self.ingest_service.ingest_bundle(
            bundle_id, self.source_asset_registry, self.new_execution()
        )

    def ingest_bundle_path(self, path: str) -> IngestRunResult:
        """Resolve one logical bundle path and ingest its canonical identifier.

        Normal ``cogni ingest --bundle`` and Python callers use this convenience
        method.  It requires an existing exact bundle, creates nothing during
        resolution, then delegates to ``ingest_bundle``.  Ingest owns deterministic
        membership order, side effects, authorization, and typed absence failures.
        """
        bundle = self.doc_bundles.resolve(path, create=False)
        return self.ingest_bundle(bundle.bundle_id)

    def new_execution(self) -> ExecutionContext:
        """Create a fresh operation identity derived from the stable context.

        Every facade action calls this factory before crossing component control
        boundaries.  Resource owns ID generation and immutable context copying;
        repeated calls intentionally differ in run/correlation IDs while retaining
        governance fields.  No persistent state or external I/O is touched.
        """
        return ExecutionContext.create(self._context)

    def describe(self) -> dict[str, Any]:
        """Return secret-free composition diagnostics without forcing lazy state.

        Applications and ``cogni describe`` use this deterministic JSON-ready view.
        It reports context, Storage, and effective Ingest settings, and includes
        catalog information only when the registry was already initialized.  It
        never starts parsers/models or exposes credentials; concurrent registry
        inspection is protected by the root lock.
        """
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
