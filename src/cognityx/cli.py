"""Unified application-facing Cognityx command line interface."""

from __future__ import annotations

import argparse
import base64
from datetime import timedelta
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
import warnings

from cognityx_ingest.control import IngestAuthorizationError
from cognityx_ingest.models import SourceAssetBatchResult
from cognityx_storage import StorageConfig, StorageRuntime

from cognityx.client import Cogni
from cognityx.ingest_config import load_ingest_configuration
from cognityx.serialization import (
    asset_deletion,
    asset_location,
    batch_registration,
    bundle_deletion,
    description,
    doc_bundle,
    gc_plan,
    gc_result,
    ingest_run,
    registration,
    source_asset,
)

_DURATION = re.compile(r"^([1-9][0-9]*)([hd])$")


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--context", dest="context_file", type=Path)
    parser.add_argument("--context-type", choices=("user", "system"))
    parser.add_argument("--principal-id")
    parser.add_argument("--tenant-id")
    parser.add_argument("--project-id")
    parser.add_argument("--workspace-id")
    parser.add_argument("--scope", action="append", default=[], metavar="KEY=VALUE")
    storage = parser.add_mutually_exclusive_group()
    storage.add_argument("--storage-config", type=Path)
    storage.add_argument("--storage-root", type=Path)
    parser.add_argument("--catalog-path", type=Path)
    parser.add_argument("--jobs-database", type=Path)
    parser.add_argument(
        "--inference-config",
        type=Path,
        help="Advanced bounded-resolution configuration.",
    )
    parser.add_argument(
        "--parser-policy",
        choices=("fixed", "rule", "fallback", "compare", "agent"),
        default=None,
        help="Advanced extraction selection policy.",
    )
    parser.add_argument(
        "--parser-backend",
        action="append",
        choices=("basic", "pymupdf", "docling"),
        help="Approved parser backend, repeatable in fallback order.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser


def _parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="cogni",
        description="Unified Cognityx SDK command line interface.",
    )
    commands = parser.add_subparsers(dest="group", required=True)

    assets = commands.add_parser(
        "asset", aliases=("assets", "sources"), help="Manage SourceAssets."
    )
    asset_commands = assets.add_subparsers(dest="action", required=True)
    add = asset_commands.add_parser("add", parents=[common])
    add.add_argument("path", type=Path)
    add.add_argument("--bundle")
    add.add_argument(
        "--structure",
        choices=("preserve", "flat"),
        default="preserve",
    )
    recursion = add.add_mutually_exclusive_group()
    recursion.add_argument(
        "--recursive", dest="recursive", action="store_true", default=True
    )
    recursion.add_argument(
        "--no-recursive", dest="recursive", action="store_false"
    )
    listing = asset_commands.add_parser("list", parents=[common])
    listing.add_argument("--bundle")
    for name in ("show", "locate"):
        leaf = asset_commands.add_parser(name, parents=[common])
        leaf.add_argument("asset_id")
    delete = asset_commands.add_parser("delete", parents=[common])
    delete.add_argument("asset_id")
    delete.add_argument("--yes", action="store_true", help="Confirm logical deletion.")
    delete.add_argument("--reason")
    asset_commands.add_parser("deleted", parents=[common])

    bundles = commands.add_parser(
        "bundle", aliases=("doc-bundles", "bundles"), help="Manage DocBundles."
    )
    bundle_commands = bundles.add_subparsers(dest="action", required=True)
    create = bundle_commands.add_parser("create", parents=[common])
    create.add_argument("path")
    bundle_commands.add_parser("list", parents=[common])
    locate = bundle_commands.add_parser("locate", parents=[common])
    locate.add_argument("bundle_id")
    delete_bundle = bundle_commands.add_parser("delete", parents=[common])
    delete_bundle.add_argument("bundle_id")
    delete_bundle.add_argument("--recursive", action="store_true")
    delete_bundle.add_argument("--yes", action="store_true", help="Confirm logical deletion.")
    delete_bundle.add_argument("--reason")
    bundle_commands.add_parser("deleted", parents=[common])

    ingest = commands.add_parser(
        "ingest", parents=[common], help="Turn PDFs into DataForge-ready documents."
    )
    ingest_input = ingest.add_mutually_exclusive_group(required=True)
    ingest_input.add_argument("path", nargs="?", type=Path)
    ingest_input.add_argument("--asset", dest="asset_id")
    ingest_input.add_argument("--bundle", dest="bundle_path")
    ingest_input.add_argument("--bundle-id")

    ingest_config = commands.add_parser(
        "ingest-config", help="Inspect effective Ingest configuration."
    )
    ingest_config_commands = ingest_config.add_subparsers(
        dest="action", required=True
    )
    ingest_config_commands.add_parser("show", parents=[common])
    ingest_config_commands.add_parser("validate", parents=[common])

    jobs = commands.add_parser(
        "job", aliases=("jobs",), help="Inspect or cancel ingest work."
    )
    job_commands = jobs.add_subparsers(dest="action", required=True)
    job_commands.add_parser("list", parents=[common])
    for name in ("status", "show", "events", "watch", "cancel"):
        leaf = job_commands.add_parser(name, parents=[common])
        leaf.add_argument("job_id")
        if name in {"events", "watch"}:
            leaf.add_argument("--after", type=int, default=0)

    runs = commands.add_parser(
        "run", aliases=("runs",), help="Inspect or remove generated ingest runs."
    )
    run_commands = runs.add_subparsers(dest="action", required=True)
    run_commands.add_parser("list", parents=[common])
    for name in ("show", "delete"):
        leaf = run_commands.add_parser(name, parents=[common])
        leaf.add_argument("run_id")
        if name == "delete":
            leaf.add_argument("--yes", action="store_true")

    documents = commands.add_parser(
        "document", aliases=("documents",), help="Inspect or remove generated documents."
    )
    document_commands = documents.add_subparsers(dest="action", required=True)
    document_commands.add_parser("list", parents=[common])
    for name in ("show", "delete"):
        leaf = document_commands.add_parser(name, parents=[common])
        leaf.add_argument("document_id")
        if name == "delete":
            leaf.add_argument("--yes", action="store_true")

    artifacts = commands.add_parser(
        "artifact", aliases=("artifacts",), help="Inspect generated document data."
    )
    artifact_commands = artifacts.add_subparsers(dest="action", required=True)
    read = artifact_commands.add_parser("read", parents=[common])
    read.add_argument("document_id")
    read.add_argument(
        "name", choices=("document", "evidence", "provenance", "manifest")
    )

    cleanup = commands.add_parser("cleanup", help="Plan or execute physical Blob cleanup.")
    cleanup_commands = cleanup.add_subparsers(dest="action", required=True)
    blobs = cleanup_commands.add_parser(
        "blobs",
        parents=[common],
        description="Blob cleanup is dry-run planning by default.",
    )
    confirmation = blobs.add_mutually_exclusive_group()
    confirmation.add_argument("--dry-run", action="store_true")
    confirmation.add_argument("--yes", action="store_true", help="Execute the fresh plan.")
    blobs.add_argument("--older-than", default="7d", metavar="DURATION")
    blobs.add_argument("--batch-size", type=int, default=100)

    describe = commands.add_parser("describe", parents=[common])
    describe.add_argument("--assets", action="store_true")
    return parser


def _scopes(values: list[str]) -> dict[str, str]:
    scopes: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Malformed --scope {value!r}; expected KEY=VALUE.")
        key, selected = value.split("=", 1)
        if not key or not selected:
            raise ValueError(f"Malformed --scope {value!r}; expected non-empty KEY=VALUE.")
        scopes[key] = selected
    return scopes


def _duration(value: str) -> timedelta:
    match = _DURATION.fullmatch(value)
    if not match:
        raise ValueError("--older-than must be a positive duration such as 1h or 7d.")
    amount, unit = int(match.group(1)), match.group(2)
    return timedelta(hours=amount) if unit == "h" else timedelta(days=amount)


def _load(args: argparse.Namespace) -> Cogni:
    overrides = {
        name: getattr(args, name)
        for name in (
            "context_type",
            "principal_id",
            "tenant_id",
            "project_id",
            "workspace_id",
        )
        if getattr(args, name, None) is not None
    }
    scopes = _scopes(getattr(args, "scope", []))
    if scopes:
        overrides["scopes"] = scopes
    runtime = None
    if getattr(args, "storage_root", None) is not None:
        warnings.warn(
            "--storage-root is deprecated; configure StorageRuntime or use --storage-config.",
            FutureWarning,
            stacklevel=3,
        )
        runtime = StorageRuntime.from_config(
            StorageConfig.built_in(root=args.storage_root)
        )
    return Cogni.load(
        context_file=getattr(args, "context_file", None),
        context_overrides=overrides or None,
        storage_runtime=runtime,
        storage_config=getattr(args, "storage_config", None),
        catalog_path=getattr(args, "catalog_path", None),
        jobs_database=getattr(args, "jobs_database", None),
        inference_config=getattr(args, "inference_config", None),
        parser_policy=getattr(args, "parser_policy", None),
        parser_backends=(
            tuple(args.parser_backend)
            if getattr(args, "parser_backend", None) is not None
            else None
        ),
    )


def _resolved_ingest_configuration(args: argparse.Namespace) -> dict[str, object]:
    selected = load_ingest_configuration(
        parser_policy=getattr(args, "parser_policy", None),
        parser_backends=getattr(args, "parser_backend", None),
        inference_enabled=(
            True if getattr(args, "inference_config", None) is not None else None
        ),
    )
    return selected.to_dict()


def _execute(args: argparse.Namespace) -> Any:
    compatibility = {
        "assets": "asset",
        "sources": "asset",
        "doc-bundles": "bundle",
        "bundles": "bundle",
        "jobs": "job",
        "runs": "run",
        "documents": "document",
        "artifacts": "artifact",
    }
    if args.group in compatibility:
        warnings.warn(
            f"'{args.group}' is deprecated; use singular '{compatibility[args.group]}'.",
            FutureWarning,
            stacklevel=3,
        )
        args.group = compatibility[args.group]
    if args.group == "ingest-config":
        selected = _resolved_ingest_configuration(args)
        if args.action == "validate":
            return {"valid": True, **selected}
        return selected
    cogni = _load(args)
    if args.group == "asset":
        if args.action == "add":
            result = cogni.assets.add(
                args.path,
                bundle=args.bundle,
                structure=args.structure,
                recursive=args.recursive,
            )
            if isinstance(result, SourceAssetBatchResult) and result.failed_count:
                print(
                    f"{result.failed_count} SourceAsset file registration(s) failed; "
                    "inspect the JSON batch items for safe details.",
                    file=sys.stderr,
                )
            return (
                batch_registration(result)
                if isinstance(result, SourceAssetBatchResult)
                else registration(result)
            )
        if args.action == "list":
            return [source_asset(item) for item in cogni.assets.list(bundle=args.bundle)]
        if args.action == "show":
            return source_asset(cogni.assets.get(args.asset_id))
        if args.action == "locate":
            return asset_location(cogni.assets.locate(args.asset_id))
        if args.action == "delete":
            if not args.yes:
                raise _ConfirmationRequired("assets delete requires --yes; no deletion was performed.")
            return asset_deletion(cogni.assets.delete(args.asset_id, reason=args.reason))
        return [source_asset(item) for item in cogni.assets.list_deleted()]
    if args.group == "bundle":
        if args.action == "create":
            return doc_bundle(cogni.doc_bundles.create(args.path))
        if args.action == "list":
            return [doc_bundle(item) for item in cogni.doc_bundles.list()]
        if args.action == "locate":
            return cogni.doc_bundles.locate(args.bundle_id)
        if args.action == "delete":
            if not args.yes:
                raise _ConfirmationRequired("doc-bundles delete requires --yes; no deletion was performed.")
            return bundle_deletion(
                cogni.doc_bundles.delete(
                    args.bundle_id, recursive=args.recursive, reason=args.reason
                )
            )
        return [doc_bundle(item) for item in cogni.doc_bundles.list_deleted()]
    if args.group == "ingest":
        if args.asset_id:
            return ingest_run(cogni.ingest_asset(args.asset_id))
        if args.bundle_path:
            return ingest_run(cogni.ingest_bundle_path(args.bundle_path))
        if args.bundle_id:
            warnings.warn(
                "--bundle-id is a compatibility form; prefer --bundle with the full path.",
                FutureWarning,
                stacklevel=3,
            )
            return ingest_run(cogni.ingest_bundle(args.bundle_id))
        return ingest_run(cogni.ingest_path(args.path))
    if args.group == "job":
        owner_id = cogni.context.principal_id or "local"
        execution = cogni.new_execution()
        if args.action == "list":
            return cogni.ingest_manager.list_jobs(execution, owner_id=owner_id)
        if args.action in {"status", "show"}:
            return cogni.ingest_manager.show_job(
                execution, args.job_id, owner_id=owner_id
            )
        if args.action == "events":
            return cogni.ingest_manager.job_events(
                execution, args.job_id, owner_id=owner_id, after=args.after
            )
        if args.action == "watch":
            _watch_job(cogni, args.job_id, owner_id=owner_id, after=args.after)
            return None
        return cogni.ingest_manager.request_cancel(
            execution, args.job_id, owner_id=owner_id
        )
    if args.group == "run":
        execution = cogni.new_execution()
        if args.action == "list":
            return cogni.ingest_manager.list_runs(execution)
        if args.action == "show":
            return cogni.ingest_manager.show_run(execution, args.run_id)
        if not args.yes:
            raise _ConfirmationRequired("runs delete requires --yes; no deletion was performed.")
        cogni.ingest_manager.delete_run(execution, args.run_id)
        return {"deleted_run_id": args.run_id}
    if args.group == "document":
        execution = cogni.new_execution()
        if args.action == "list":
            return cogni.ingest_manager.list_documents(execution)
        if args.action == "show":
            return cogni.ingest_manager.show_document(execution, args.document_id)
        if not args.yes:
            raise _ConfirmationRequired("documents delete requires --yes; no deletion was performed.")
        cogni.ingest_manager.delete_document(execution, args.document_id)
        return {"deleted_document_id": args.document_id}
    if args.group == "artifact":
        payload = cogni.ingest_manager.read_artifact(
            cogni.new_execution(), args.document_id, args.name
        )
        return _artifact(args.name, payload)
    if args.group == "cleanup":
        if not 1 <= args.batch_size <= 500:
            raise ValueError("--batch-size must be between 1 and 500.")
        plan = cogni.cleanup.plan_blobs(older_than=_duration(args.older_than))
        if not args.yes:
            payload = gc_plan(plan)
            payload["dry_run"] = True
            return payload
        result = cogni.cleanup.execute_blobs(plan, batch_size=args.batch_size)
        return {
            "dry_run": False,
            "plan": {
                "plan_id": plan.plan_id,
                "candidate_count": len(plan.deletion_candidates),
                "reclaimable_bytes": plan.reclaimable_bytes,
            },
            "result": gc_result(result),
        }
    if args.assets:
        cogni.source_asset_registry
    return description(cogni.describe())


class _ConfirmationRequired(ValueError):
    pass


def _watch_job(cogni: Cogni, job_id: str, *, owner_id: str, after: int) -> None:
    terminal = {"completed", "failed", "cancelled", "interrupted"}
    while True:
        execution = cogni.new_execution()
        events = cogni.ingest_manager.job_events(
            execution, job_id, owner_id=owner_id, after=after
        )
        for event in events:
            print(json.dumps(event, sort_keys=True), flush=True)
            after = int(event["sequence"])
        status = cogni.ingest_manager.show_job(
            execution, job_id, owner_id=owner_id
        )["job"]["state"]
        if status in terminal:
            return
        time.sleep(0.25)


def _artifact(name: str, payload: bytes) -> dict[str, Any]:
    try:
        return {"artifact": name, "encoding": "utf-8", "content": payload.decode("utf-8")}
    except UnicodeDecodeError:
        return {
            "artifact": name,
            "encoding": "base64",
            "content": base64.b64encode(payload).decode("ascii"),
        }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        payload = _execute(args)
    except _ConfirmationRequired as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ValueError, argparse.ArgumentError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except IngestAuthorizationError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    except Exception as exc:
        if getattr(args, "debug", False):
            raise
        print(str(exc), file=sys.stderr)
        return 1
    if payload is not None:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
