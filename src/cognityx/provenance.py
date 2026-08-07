"""Resolve persisted provenance addresses through the document's own artifacts.

This module provides the user-facing bridge to Ingest's settled deterministic
address resolver.  It reads the authorized document's Source Graph and address
catalog through ``Cogni.artifacts``, invokes strict public Ingest readers, resolves
one exact address ID, and projects the immutable result to a safe JSON-ready
mapping.  It never reopens source files, parser-native payloads, models, or
networks, and it cannot substitute a graph or catalog from another document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cognityx_ingest import (
    AddressResolution,
    ProvenanceAddressCatalog,
    ProvenanceAddressResolver,
    ProvenanceTarget,
    SourceGraph,
)

if TYPE_CHECKING:
    from cognityx.client import Cogni


class Provenance:
    """Expose deterministic, text-free provenance address resolution.

    ``Cogni`` constructs this facade lazily for Python and CLI callers.  It keeps
    no graph cache, so every request reuses the normal document authorization and
    immutable artifact integrity checks.  Resolution is deterministic and
    read-only; strict graph/address validation failures remain typed Ingest
    exceptions, while forbidden outcomes are safely redacted by the resolver.
    """

    def __init__(self, owner: "Cogni") -> None:
        """Attach to one SDK owner without loading documents or inference.

        The ``Cogni.provenance`` property is the intended constructor.  The owner
        supplies the closed artifact facade and execution context.  Construction
        has no I/O, side effects, persistence, or mutable shared state.
        """
        self._owner = owner

    def resolve(self, document_id: str, address_id: str) -> dict[str, object]:
        """Resolve one exact address from its document-owned graph and catalog.

        Python and CLI callers provide opaque IDs.  The algorithm independently
        authorizes both settled artifact reads, strictly parses production JSON,
        constructs Ingest's conservative resolver, and returns a safe structured
        projection preserving all six statuses.  No caller can inject foreign
        bytes or a URI.  The method is idempotent for immutable artifacts, starts
        no parser/model/network work, and propagates typed validation/revision or
        authorization failures before returning any target detail.
        """
        graph_payload = self._owner.artifacts.read(document_id, "source-graph")
        catalog_payload = self._owner.artifacts.read(
            document_id, "provenance-addresses"
        )
        graph = SourceGraph.from_json_bytes(graph_payload)
        catalog = ProvenanceAddressCatalog.from_json_bytes(catalog_payload)
        result = ProvenanceAddressResolver(graph, catalog).resolve(address_id)
        return _resolution_dict(result)


def _resolution_dict(result: AddressResolution) -> dict[str, object]:
    """Project a validated resolver result without broad object serialization.

    ``Provenance.resolve`` calls this after Ingest resolution.  It validates the
    closed status shape, emits common bounded metadata, and conditionally emits
    only target, candidate, or member fields already permitted by T08.  Explicit
    projection prevents future private/source fields from leaking automatically.
    Input order is preserved, the function is pure, and malformed direct results
    raise the resolver's typed validation exception.
    """
    result.validate()
    payload: dict[str, object] = {
        "address_id": result.address_id,
        "status": result.status,
        "reason": result.reason,
    }
    if result.graph_revision is not None:
        payload["graph_revision"] = result.graph_revision
    if result.target is not None:
        payload["target"] = _target_dict(result.target)
    if result.targets:
        payload["targets"] = [_target_dict(item) for item in result.targets]
    if result.candidate_targets:
        payload["candidate_targets"] = [
            _target_dict(item) for item in result.candidate_targets
        ]
    if result.member_resolutions:
        payload["member_resolutions"] = [
            _resolution_dict(item) for item in result.member_resolutions
        ]
    return payload


def _target_dict(target: ProvenanceTarget) -> dict[str, object]:
    """Project one validated target to identifiers and an optional text range.

    The resolution serializer calls this only for details Ingest has authorized
    for the outcome.  Exactly one canonical ID is emitted, followed by a complete
    character range only when present.  No source text, selector, native payload,
    URI, or physical path exists in the output.  The pure function preserves the
    target's validated shape and raises typed validation failures on bad input.
    """
    target.validate()
    payload: dict[str, object] = {}
    for name in ("node_id", "division_id", "representation_id"):
        value = getattr(target, name)
        if value is not None:
            payload[name] = value
    if target.char_start is not None:
        payload["char_start"] = target.char_start
        payload["char_end"] = target.char_end
    return payload
