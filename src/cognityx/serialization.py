"""Explicit public JSON serialization for SDK and CLI values."""

from __future__ import annotations

from typing import Any

from cognityx_ingest import (
    DocBundle,
    DocBundleDeletionResult,
    SourceAsset,
    SourceAssetBatchResult,
    SourceAssetDeletionResult,
    SourceAssetLocation,
    SourceAssetRegistrationResult,
)
from cognityx_storage import BlobGcPlan, BlobGcResult


def source_asset(item: SourceAsset) -> dict[str, Any]:
    return {
        "asset_id": item.asset_id,
        "context_id": item.context_id,
        "bundle_id": item.bundle_id,
        "original_filename": item.original_filename,
        "media_type": item.media_type,
        "size_bytes": item.size_bytes,
        "sha256": item.sha256,
        "blob_id": item.blob_id,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "deleted_at": item.deleted_at,
        "deleted_by": item.deleted_by,
        "delete_run_id": item.delete_run_id,
        "delete_reason": item.delete_reason,
    }


def registration(item: SourceAssetRegistrationResult) -> dict[str, Any]:
    return {
        "asset_id": item.asset_id,
        "context_id": item.context_id,
        "bundle_id": item.bundle_id,
        "sha256": item.sha256,
        "size_bytes": item.size_bytes,
        "status": item.status,
    }


def batch_registration(item: SourceAssetBatchResult) -> dict[str, Any]:
    return {
        "batch_id": item.batch_id,
        "context_id": item.context_id,
        "root_bundle_id": item.root_bundle_id,
        "root_bundle_path": item.root_bundle_path,
        "structure": item.structure,
        "recursive": item.recursive,
        "files_discovered": item.files_discovered,
        "files_processed": item.files_processed,
        "created_count": item.created_count,
        "restored_count": item.restored_count,
        "already_registered_count": item.already_registered_count,
        "failed_count": item.failed_count,
        "skipped_count": item.skipped_count,
        "items": [
            {
                "relative_path": selected.relative_path,
                "bundle_path": selected.bundle_path,
                "asset_id": selected.asset_id,
                "status": selected.status,
                "error_category": selected.error_category,
                "error_message": selected.error_message,
            }
            for selected in item.items
        ],
    }


def asset_deletion(item: SourceAssetDeletionResult) -> dict[str, Any]:
    return {
        "asset_id": item.asset_id,
        "context_id": item.context_id,
        "bundle_id": item.bundle_id,
        "blob_id": item.blob_id,
        "deleted_at": item.deleted_at,
        "status": item.status,
        "blob_still_referenced": item.blob_still_referenced,
    }


def asset_location(item: SourceAssetLocation) -> dict[str, Any]:
    return {
        "asset_id": item.asset_id,
        "blob_id": item.blob_id,
        "blob_uri": item.blob_uri,
        "backend": item.backend,
        "local_path": item.local_path,
        "profile_name": item.profile_name,
    }


def doc_bundle(item: DocBundle) -> dict[str, Any]:
    return {
        "bundle_id": item.bundle_id,
        "context_id": item.context_id,
        "name": item.name,
        "path": item.path,
        "parent_bundle_id": item.parent_bundle_id,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "deleted_at": item.deleted_at,
        "deleted_by": item.deleted_by,
        "delete_run_id": item.delete_run_id,
        "delete_reason": item.delete_reason,
    }


def bundle_deletion(item: DocBundleDeletionResult) -> dict[str, Any]:
    return {
        "bundle_id": item.bundle_id,
        "context_id": item.context_id,
        "deleted_asset_count": item.deleted_asset_count,
        "deleted_bundle_count": item.deleted_bundle_count,
        "deleted_at": item.deleted_at,
        "status": item.status,
    }


def gc_plan(item: BlobGcPlan) -> dict[str, Any]:
    return item.to_dict()


def gc_result(item: BlobGcResult) -> dict[str, Any]:
    return item.to_dict()


def description(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_id": item.get("context_id"),
        "context_type": item.get("context_type"),
        "principal_id": item.get("principal_id"),
        "tenant_id": item.get("tenant_id"),
        "project_id": item.get("project_id"),
        "workspace_id": item.get("workspace_id"),
        "storage": _redact(item.get("storage")),
        "source_asset_catalog": item.get("source_asset_catalog"),
    }


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(word in key.lower() for word in ("password", "secret", "token", "credential", "api_key"))
                else _redact(selected)
            )
            for key, selected in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
