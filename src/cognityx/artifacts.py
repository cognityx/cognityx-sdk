"""Expose a closed, authorization-preserving view of settled Ingest artifacts.

This module exists so SDK and CLI callers can inspect durable document outputs
without learning Storage keys or physical paths.  ``Artifacts`` first crosses
the Ingest document-read authorization boundary, maps one canonical public name
to a fixed manifest entry and logical filename, verifies the manifest URI against
the configured artifact role, and only then locates or opens the object.  The
closed mapping is the security boundary: arbitrary URIs, traversal strings, and
parser-native payloads are never interpreted as artifact names.

The facade is constructed lazily by :class:`cognityx.client.Cogni`.  It keeps no
mutable cache, performs no parser or model work, and is safe to reuse under the
same thread-safety assumptions as the owner composition root.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from cognityx.client import Cogni


@dataclass(frozen=True, slots=True)
class _ArtifactDescriptor:
    """Bind one public artifact name to its persisted manifest and file names.

    ``Artifacts`` owns these descriptors as immutable process constants.  They
    encode settled Ingest persistence facts rather than accepting caller input,
    which makes URI verification deterministic and prevents path construction
    from untrusted strings.  Construction has no side effects; invalid manifest
    content is rejected later with ``ValueError`` at the SDK trust boundary.
    """

    manifest_name: str | None
    filename: str


_SUPPORTED_ARTIFACTS: Mapping[str, _ArtifactDescriptor] = MappingProxyType(
    {
        "document": _ArtifactDescriptor("document", "document.json"),
        "evidence": _ArtifactDescriptor("evidence", "evidence.jsonl"),
        "provenance": _ArtifactDescriptor("provenance", "provenance.json"),
        "manifest": _ArtifactDescriptor(None, "manifest.json"),
        "canonical-content": _ArtifactDescriptor(
            "canonical_content", "canonical-content.json"
        ),
        "source-graph": _ArtifactDescriptor("source_graph", "source-graph.json"),
        "provenance-addresses": _ArtifactDescriptor(
            "provenance_addresses", "provenance-addresses.json"
        ),
        "parser-observations": _ArtifactDescriptor(
            "parser_observations", "parser/observations.json"
        ),
        "parser-fusion-decisions": _ArtifactDescriptor(
            "parser_fusion_decisions", "parser/fusion-decisions.json"
        ),
    }
)

ARTIFACT_NAMES = tuple(_SUPPORTED_ARTIFACTS)


class Artifacts:
    """Read and locate settled document artifacts without exposing storage paths.

    ``Cogni`` constructs this facade lazily and CLI/Python callers invoke it with
    a document ID plus one name from :data:`ARTIFACT_NAMES`.  Every operation
    authorizes through ``IngestManager.show_document`` before inspecting the
    manifest.  The facade has no cache or persistence of its own, preserves the
    mapping's deterministic order, and never initializes parsers or inference.
    Authorization, missing objects, and malformed manifests retain their typed
    component failures; unsupported names fail as ``ValueError``.
    """

    def __init__(self, owner: "Cogni") -> None:
        """Attach the facade to one SDK composition root without doing I/O.

        ``Cogni.artifacts`` is the sole normal constructor.  The owner supplies a
        shared execution context factory, Ingest authorization boundary, and
        configured Storage runtime.  Construction is lazy and side-effect free;
        each later call creates its own execution and performs fresh validation.
        """
        self._owner = owner

    def available(self, document_id: str) -> tuple[str, ...]:
        """Return supported settled names actually present for one document.

        Python and CLI inspection callers use this to discover optional parser
        observation/fusion outputs.  The algorithm authorizes and reads the
        document manifest, always includes the fixed manifest itself, then emits
        present names in ``ARTIFACT_NAMES`` order.  It performs no object reads,
        reveals no URI or path, and repeats idempotently for an unchanged
        immutable document.
        """
        manifest = self._authorized_manifest(document_id)
        persisted = self._manifest_artifacts(manifest)
        return tuple(
            name
            for name, descriptor in _SUPPORTED_ARTIFACTS.items()
            if descriptor.manifest_name is None
            or descriptor.manifest_name in persisted
        )

    def read(self, document_id: str, name: str) -> bytes:
        """Read one settled artifact after authorization and URI verification.

        CLI and Python callers receive the exact persisted bytes.  The method
        rejects unsupported names before any path construction, authorizes the
        document, proves that its manifest URI equals the configured artifact
        store URI for the fixed filename, and opens that logical key through the
        public role store.  It never follows caller-provided URIs, exposes local
        paths, starts inference, or mutates storage; component open failures and
        clean ``ValueError`` trust-boundary failures propagate to the caller.
        """
        _descriptor, key, _uri = self._resolve(document_id, name)
        with self._owner.storage.for_role("artifact").open(key) as source:
            return source.read()

    def locate(self, document_id: str, name: str) -> dict[str, object]:
        """Return safe logical location metadata for one settled artifact.

        Automation callers use this when they need existence and size rather than
        bytes.  Resolution follows the same authorization and exact-URI checks as
        ``read``.  Storage supplies canonical metadata, after which the physical
        ``local_path`` field is removed unconditionally.  The returned mapping is
        deterministic, contains no secret material, performs no writes, and may
        report ``exists=False`` for a logically valid missing object.
        """
        _descriptor, _key, uri = self._resolve(document_id, name)
        location = self._owner.storage.locate(uri).to_dict()
        location.pop("local_path", None)
        return {
            "document_id": document_id,
            "name": name,
            "location": location,
        }

    def _resolve(
        self, document_id: str, name: str
    ) -> tuple[_ArtifactDescriptor, str, str]:
        """Authorize and bind a public name to one verified logical object.

        ``read`` and ``locate`` share this trust-boundary helper to avoid policy
        drift.  It validates the closed name table, obtains the document's own
        manifest, verifies required entries and URI types, derives one fixed key,
        and compares the persisted URI byte-for-byte with the configured role
        store's public URI.  No filesystem operation occurs here.  Unsupported,
        absent, or forged references fail cleanly as ``ValueError``.
        """
        descriptor = self._descriptor(name)
        manifest = self._authorized_manifest(document_id)
        expected_key = f"ingest/documents/{document_id}/{descriptor.filename}"
        expected_uri = self._owner.storage.for_role("artifact").uri(expected_key)
        if descriptor.manifest_name is not None:
            artifacts = self._manifest_artifacts(manifest)
            try:
                entry = artifacts[descriptor.manifest_name]
                persisted_uri = entry["uri"]
            except (KeyError, TypeError) as error:
                raise ValueError(
                    f"Artifact {name!r} is not available for document {document_id!r}."
                ) from error
            if not isinstance(persisted_uri, str):
                raise ValueError(f"Artifact {name!r} has an invalid manifest URI.")
            if persisted_uri != expected_uri:
                raise ValueError(
                    f"Artifact {name!r} does not match its configured Storage URI."
                )
        return descriptor, expected_key, expected_uri

    def _authorized_manifest(self, document_id: str) -> Mapping[str, object]:
        """Cross the Ingest read boundary and return the document's manifest.

        All facade operations call this helper before reading artifact metadata or
        bytes.  ``IngestManager`` validates the canonical document ID, authorizes
        the fresh execution, and strictly reads the document-owned manifest.  The
        helper performs no fallback or cross-document substitution and raises
        ``ValueError`` when a non-mapping payload crosses the component boundary.
        """
        document = self._owner.ingest_manager.show_document(
            self._owner.new_execution(), document_id
        )
        try:
            manifest = document["manifest"]
        except (KeyError, TypeError) as error:
            raise ValueError("Ingest document response has no manifest.") from error
        if not isinstance(manifest, Mapping):
            raise ValueError("Ingest document manifest must be a mapping.")
        return manifest

    @staticmethod
    def _descriptor(name: str) -> _ArtifactDescriptor:
        """Select one exact public descriptor without aliases or normalization.

        Artifact operations call this before using the name.  Exact matching is
        intentional: it keeps deterministic hyphenated vocabulary and ensures
        traversal strings, URI schemes, and internal underscore names are merely
        unsupported values.  The pure lookup returns immutable process data or a
        bounded ``ValueError`` listing the allowed names.
        """
        try:
            return _SUPPORTED_ARTIFACTS[name]
        except (KeyError, TypeError) as error:
            available = ", ".join(ARTIFACT_NAMES)
            raise ValueError(
                f"Unknown artifact {name!r}; choose one of: {available}."
            ) from error

    @staticmethod
    def _manifest_artifacts(
        manifest: Mapping[str, object],
    ) -> Mapping[str, Mapping[str, object]]:
        """Validate the minimal manifest collection needed by this facade.

        Discovery and read operations call this on authorized component output.
        The helper deliberately validates only the mapping boundary it consumes,
        leaving full schema ownership with Ingest.  It does no I/O or mutation;
        malformed values fail as ``ValueError`` before a URI can be trusted.
        """
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError("Ingest document manifest has no artifact mapping.")
        return artifacts
