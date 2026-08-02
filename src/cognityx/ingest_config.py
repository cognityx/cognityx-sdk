"""Configuration-first parser and bounded-inference selection for Ingest."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from typing import Mapping, Sequence


PARSER_POLICIES = frozenset({"fixed", "rule", "fallback", "compare", "agent"})
PARSER_BACKENDS = frozenset({"basic", "pymupdf", "docling"})
_DEFAULT_POLICY = "fixed"
_DEFAULT_BACKENDS = ("basic",)


@dataclass(frozen=True, slots=True)
class IngestConfiguration:
    """Resolved effective settings with an audit source for every value."""

    parser_policy: str
    parser_backends: tuple[str, ...]
    inference_enabled: bool
    sources: Mapping[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "ingest": {
                "parser_policy": self.parser_policy,
                "parser_backends": list(self.parser_backends),
                "inference": {"enabled": self.inference_enabled},
            },
            "sources": {
                "parser_policy": self.sources["parser_policy"],
                "parser_backends": self.sources["parser_backends"],
                "inference.enabled": self.sources["inference_enabled"],
            },
        }


def load_ingest_configuration(
    *,
    cwd: str | Path | None = None,
    user_config_file: str | Path | None = None,
    parser_policy: str | None = None,
    parser_backends: Sequence[str] | None = None,
    inference_enabled: bool | None = None,
) -> IngestConfiguration:
    """Resolve built-in, user, project, environment, and CLI settings."""
    values: dict[str, object] = {
        "parser_policy": _DEFAULT_POLICY,
        "parser_backends": _DEFAULT_BACKENDS,
        "inference_enabled": False,
    }
    sources = {name: "built-in defaults" for name in values}

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
        raise FileNotFoundError(
            f"COGNITYX_INGEST_CONFIG does not exist: {environment}"
        )

    for label, path in (
        ("user", user),
        ("project", project),
        ("environment", environment),
    ):
        if path is None or not path.is_file():
            continue
        for name, value in _read_ingest_file(path).items():
            values[name] = value
            sources[name] = f"{label}:{path}"

    cli_values = {
        "parser_policy": parser_policy,
        "parser_backends": (
            tuple(parser_backends) if parser_backends is not None else None
        ),
        "inference_enabled": inference_enabled,
    }
    for name, value in cli_values.items():
        if value is not None:
            values[name] = value
            sources[name] = "cli"

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
    )


def _read_ingest_file(path: Path) -> dict[str, object]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
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
            f"Unsupported [ingest] setting in {path}: "
            + ", ".join(sorted(unsupported))
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
            selected["inference_enabled"] = _validate_inference(
                inference["enabled"]
            )
    return selected


def _validate_policy(value: object) -> str:
    if not isinstance(value, str) or value not in PARSER_POLICIES:
        choices = ", ".join(sorted(PARSER_POLICIES))
        raise ValueError(
            f"Invalid ingest parser_policy {value!r}; expected one of {choices}."
        )
    return value


def _validate_backends(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("ingest parser_backends must be a non-empty list.")
    selected = tuple(value)
    if any(
        not isinstance(item, str) or item not in PARSER_BACKENDS
        for item in selected
    ):
        choices = ", ".join(sorted(PARSER_BACKENDS))
        raise ValueError(
            f"Invalid ingest parser_backends {list(selected)!r}; expected {choices}."
        )
    if len(set(selected)) != len(selected):
        raise ValueError("ingest parser_backends must not contain duplicates.")
    return selected


def _validate_inference(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("ingest.inference.enabled must be true or false.")
    return value
