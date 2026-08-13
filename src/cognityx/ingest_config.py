"""Resolve the real, executable Ingest controls from layered local settings.

This module is the SDK's single configuration control plane for parser policy,
ordered parser backends, and bounded-inference enablement.  It overlays safe
built-ins, user configuration, project configuration, an environment-selected
configuration file, and explicit invocation overrides independently per value.
Strict TOML readers reject unknown or contradictory input before parsing a
document or contacting a model.

Adaptive v3.2 routing is intentionally reported only as a derived planning
classification.  The merged Ingest composition has no provider-to-parser
execution bridge for all three adaptive modes, so this module does not accept a
``routing.mode`` key or flag that would be ignored at runtime.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from cognityx_ingest import ExtractionPolicy, adaptive_mode_for_legacy_policy

PARSER_POLICIES = frozenset({"fixed", "rule", "fallback", "compare", "agent"})
PARSER_BACKENDS = frozenset({"basic", "pymupdf", "docling"})
_DEFAULT_POLICY = "fixed"
_DEFAULT_BACKENDS = ("basic",)


@dataclass(frozen=True, slots=True)
class IngestConfiguration:
    """Carry validated executable settings and the source of every value.

    ``load_ingest_configuration`` constructs this immutable record after all
    overlays and cross-setting checks.  ``Cogni`` consumes its three executable
    values to build the existing parser path; CLI inspection consumes ``sources``
    for a secret-free audit.  The record owns no files or clients, is safe to
    share across threads, and produces deterministic output for equal inputs.
    """

    parser_policy: str
    parser_backends: tuple[str, ...]
    inference_enabled: bool
    sources: Mapping[str, str]
    config_layers: tuple[Mapping[str, object], ...] = ()
    field_sources: Mapping[str, str] | None = None
    overrides: tuple[Mapping[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return secret-free execution settings plus derived routing context.

        ``cogni ingest-config show``, ``validate``, and ``Cogni.describe`` call
        this serializer.  It preserves executable values and their per-value
        sources, then derives the T04 analogue of the active legacy parser policy
        without planning or executing a parser.  The explicit ``execution_active``
        marker prevents consumers from mistaking that classification for a live
        adaptive routing control.  The method is pure and deterministic.
        """
        adaptive_mode = adaptive_mode_for_legacy_policy(
            ExtractionPolicy(self.parser_policy, self.parser_backends)
        )
        return {
            "ingest": {
                "parser_policy": self.parser_policy,
                "parser_backends": list(self.parser_backends),
                "inference": {"enabled": self.inference_enabled},
                "routing": {
                    "adaptive_mode": adaptive_mode,
                    "execution_active": False,
                    "execution_control": "parser_policy",
                    "classification": "planning-only",
                },
            },
            "sources": {
                "parser_policy": self.sources["parser_policy"],
                "parser_backends": self.sources["parser_backends"],
                "inference.enabled": self.sources["inference_enabled"],
                "routing.adaptive_mode": "derived:ingest.parser_policy",
            },
        }

    def diagnostic_dict(self) -> dict[str, object]:
        """Return the standard static configuration diagnostic contract."""
        compatible = self.to_dict()
        layers = [dict(layer) for layer in self.config_layers]
        master = layers[-1] if layers else None
        return {
            "component": "ingest",
            "configuration_kind": "persistent-component",
            "valid": True,
            "master_config": {
                "kind": "file" if master is not None else "built-in",
                "path": master["path"] if master is not None else None,
                "selected_by": master["selected_by"]
                if master is not None
                else "built-in",
                "sha256": master["sha256"] if master is not None else None,
            },
            "config_layers": layers,
            "field_sources": dict(self.field_sources or {}),
            "overrides": [dict(item) for item in self.overrides],
            "effective": compatible["ingest"],
            "warnings": [],
            "errors": [],
        }


def load_ingest_configuration(
    *,
    config_file: str | Path | None = None,
    cwd: str | Path | None = None,
    user_config_file: str | Path | None = None,
    parser_policy: str | None = None,
    parser_backends: Sequence[str] | None = None,
    inference_enabled: bool | None = None,
) -> IngestConfiguration:
    """Resolve all supported settings with independent precedence per value.

    ``Cogni.load`` and config CLI commands call this function before constructing
    parsers or inference clients.  It overlays built-ins, user, project,
    ``COGNITYX_INGEST_CONFIG``, and explicit arguments in that order, validates
    each selected value, and rejects ``agent`` unless bounded inference is
    enabled.  Reads are local and deterministic; no document, model, network, or
    persistent state is touched.  Missing environment-selected files raise
    ``FileNotFoundError`` and malformed/unsupported settings raise ``ValueError``.
    """
    values: dict[str, object] = {
        "parser_policy": _DEFAULT_POLICY,
        "parser_backends": _DEFAULT_BACKENDS,
        "inference_enabled": False,
    }
    sources = {name: "built-in defaults" for name in values}
    diagnostic_sources = {
        "parser_policy": "built-in",
        "parser_backends": "built-in",
        "inference.enabled": "built-in",
    }
    layers: list[Mapping[str, object]] = []

    project = Path(cwd or Path.cwd()) / ".cognityx" / "ingest.toml"
    user = (
        Path(user_config_file)
        if user_config_file is not None
        else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "cognityx"
        / "ingest.toml"
    )
    configured = os.environ.get("COGNITYX_INGEST_CONFIG")
    environment = Path(configured) if configured else None
    if environment is not None and not environment.is_file():
        raise FileNotFoundError(f"COGNITYX_INGEST_CONFIG does not exist: {environment}")

    explicit = Path(config_file) if config_file is not None else None
    if explicit is not None and not explicit.is_file():
        raise FileNotFoundError(f"Ingest config file does not exist: {explicit}")

    for label, path in (
        ("user", user),
        ("project", project),
        ("environment", environment),
        ("explicit", explicit),
    ):
        if path is None or not path.is_file():
            continue
        selected_path = path.expanduser().resolve()
        raw = selected_path.read_bytes()
        changed_keys: list[str] = []
        for name, value in _read_ingest_bytes(raw, selected_path).items():
            previous = values[name]
            values[name] = value
            sources[name] = f"{label}:{path}"
            dotted = "inference.enabled" if name == "inference_enabled" else name
            if previous != value:
                changed_keys.append(dotted)
                diagnostic_sources[dotted] = str(selected_path)
        layers.append(
            {
                "path": str(selected_path),
                "selected_by": label,
                "sha256": sha256(raw).hexdigest(),
                "changed_keys": sorted(changed_keys),
            }
        )

    cli_values = {
        "parser_policy": parser_policy,
        "parser_backends": (
            tuple(parser_backends) if parser_backends is not None else None
        ),
        "inference_enabled": inference_enabled,
    }
    actual_overrides: list[Mapping[str, object]] = []
    override_sources = {
        "parser_policy": "--parser-policy",
        "parser_backends": "--parser-backend",
        "inference_enabled": "python-argument",
    }
    for name, value in cli_values.items():
        if value is not None:
            previous = values[name]
            values[name] = value
            if previous != value:
                sources[name] = "cli"
                dotted = "inference.enabled" if name == "inference_enabled" else name
                diagnostic_sources[dotted] = override_sources[name]
                actual_overrides.append(
                    {
                        "key": dotted,
                        "source": override_sources[name],
                        "previous": list(previous)
                        if isinstance(previous, tuple)
                        else previous,
                        "effective": list(value) if isinstance(value, tuple) else value,
                        "changed": True,
                    }
                )

    selected_policy = _validate_policy(values["parser_policy"])
    selected_backends = _validate_backends(values["parser_backends"])
    selected_inference = _validate_inference(values["inference_enabled"])
    if selected_policy == "agent" and not selected_inference:
        raise ValueError(
            "Parser policy 'agent' requires ingest.inference.enabled = true."
        )
    return IngestConfiguration(
        parser_policy=selected_policy,
        parser_backends=selected_backends,
        inference_enabled=selected_inference,
        sources=sources,
        config_layers=tuple(layers),
        field_sources=diagnostic_sources,
        overrides=tuple(actual_overrides),
    )


def _read_ingest_file(path: Path) -> dict[str, object]:
    """Read one strict local TOML overlay into normalized executable values.

    The layering function calls this for existing user, project, and environment
    files.  It decodes TOML, permits only the established ``[ingest]`` and
    ``[ingest.inference]`` fields, validates each present value, and returns only
    that file's partial overlay.  It performs one local read, never expands
    secrets or contacts external services, preserves parser order, and reports
    malformed or unknown input as bounded ``ValueError`` failures.
    """
    return _read_ingest_bytes(path.read_bytes(), path)


def _read_ingest_bytes(raw: bytes, path: Path) -> dict[str, object]:
    try:
        value = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid Ingest TOML in {path}: {exc}") from None
    unsupported_top = set(value) - {"ingest"}
    if unsupported_top:
        raise ValueError(
            f"Unsupported Ingest configuration section in {path}: "
            + ", ".join(sorted(unsupported_top))
        )
    ingest = value.get("ingest", {})
    if not isinstance(ingest, dict):
        raise ValueError(f"[ingest] must be a TOML table in {path}.")
    unsupported = set(ingest) - {"parser_policy", "parser_backends", "inference"}
    if unsupported:
        raise ValueError(
            f"Unsupported [ingest] setting in {path}: " + ", ".join(sorted(unsupported))
        )

    selected: dict[str, object] = {}
    if "parser_policy" in ingest:
        selected["parser_policy"] = _validate_policy(ingest["parser_policy"])
    if "parser_backends" in ingest:
        selected["parser_backends"] = _validate_backends(ingest["parser_backends"])
    if "inference" in ingest:
        inference = ingest["inference"]
        if not isinstance(inference, dict):
            raise ValueError(f"[ingest.inference] must be a TOML table in {path}.")
        unsupported_inference = set(inference) - {"enabled"}
        if unsupported_inference:
            raise ValueError(
                f"Unsupported [ingest.inference] setting in {path}: "
                + ", ".join(sorted(unsupported_inference))
            )
        if "enabled" in inference:
            selected["inference_enabled"] = _validate_inference(inference["enabled"])
    return selected


def _validate_policy(value: object) -> str:
    """Validate one executable legacy parser policy without normalization.

    File and final configuration validation call this pure helper.  Exact string
    matching preserves the existing five-policy contract and prevents an unknown
    value from silently selecting a fallback.  It returns the original string or
    raises ``ValueError``; it performs no parser construction or side effect.
    """
    if not isinstance(value, str) or value not in PARSER_POLICIES:
        choices = ", ".join(sorted(PARSER_POLICIES))
        raise ValueError(
            f"Invalid ingest parser_policy {value!r}; expected one of {choices}."
        )
    return value


def _validate_backends(value: object) -> tuple[str, ...]:
    """Validate a nonempty, unique, ordered parser backend selection.

    TOML and final overlay validation call this helper before ``Cogni`` builds an
    ``ExtractionPolicy``.  It accepts only list/tuple input from the closed backend
    vocabulary, preserves user fallback order, rejects duplicates, and returns an
    immutable tuple.  The algorithm is pure, idempotent, and raises ``ValueError``
    without importing or executing any parser adapter.
    """
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("ingest parser_backends must be a non-empty list.")
    selected = tuple(value)
    if any(
        not isinstance(item, str) or item not in PARSER_BACKENDS for item in selected
    ):
        choices = ", ".join(sorted(PARSER_BACKENDS))
        raise ValueError(
            f"Invalid ingest parser_backends {list(selected)!r}; expected {choices}."
        )
    if len(set(selected)) != len(selected):
        raise ValueError("ingest parser_backends must not contain duplicates.")
    return selected


def _validate_inference(value: object) -> bool:
    """Require an explicit boolean for bounded-inference enablement.

    Config readers call this pure type check so strings or numbers cannot
    accidentally activate a model-backed path.  The same boolean is returned;
    non-booleans raise ``ValueError``.  No configuration file, client, model, or
    network resource is loaded here.
    """
    if not isinstance(value, bool):
        raise ValueError("ingest.inference.enabled must be true or false.")
    return value
