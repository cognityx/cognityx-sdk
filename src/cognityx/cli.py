"""Unified application-facing Cognityx command line interface."""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path
import re
import sys
from typing import Any

from cognityx_ingest.control import IngestAuthorizationError
from cognityx_ingest.models import SourceAssetBatchResult
from cognityx_storage import StorageConfig, StorageRuntime

from cognityx.client import Cogni
from cognityx.serialization import (
    asset_deletion,
    asset_location,
    batch_registration,
    bundle_deletion,
    description,
    doc_bundle,
    gc_plan,
    gc_result,
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
    parser.add_argument("--debug", action="store_true")
    return parser


def _parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="cogni",
        description="Unified Cognityx SDK command line interface.",
    )
    commands = parser.add_subparsers(dest="group", required=True)

    assets = commands.add_parser("assets", help="Manage SourceAssets.")
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

    bundles = commands.add_parser("doc-bundles", help="Manage DocBundles.")
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
        runtime = StorageRuntime.from_config(
            StorageConfig.built_in(root=args.storage_root)
        )
    return Cogni.load(
        context_file=getattr(args, "context_file", None),
        context_overrides=overrides or None,
        storage_runtime=runtime,
        storage_config=getattr(args, "storage_config", None),
        catalog_path=getattr(args, "catalog_path", None),
    )


def _execute(args: argparse.Namespace) -> Any:
    cogni = _load(args)
    if args.group == "assets":
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
    if args.group == "doc-bundles":
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
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
