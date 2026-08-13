from __future__ import annotations

import json
from pathlib import Path

import pytest
from cognityx_storage import StorageConfig, StorageRuntime

from cognityx import Cogni, load_ingest_configuration
from cognityx.cli import main


def _write_config(
    path: Path,
    *,
    policy: str | None = None,
    backends: tuple[str, ...] | None = None,
    inference: bool | None = None,
) -> None:
    lines = ["[ingest]"]
    if policy is not None:
        lines.append(f'parser_policy = "{policy}"')
    if backends is not None:
        selected = ", ".join(f'"{item}"' for item in backends)
        lines.append(f"parser_backends = [{selected}]")
    if inference is not None:
        lines.extend(("", "[ingest.inference]", f"enabled = {str(inference).lower()}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_ingest_configuration_precedence_is_per_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "user.toml"
    project = tmp_path / "project"
    environment = tmp_path / "environment.toml"
    _write_config(user, policy="rule", backends=("basic",), inference=True)
    _write_config(project / ".cognityx/ingest.toml", policy="compare", inference=False)
    _write_config(
        environment,
        policy="rule",
        backends=("pymupdf", "docling", "basic"),
    )
    monkeypatch.setenv("COGNITYX_INGEST_CONFIG", str(environment))

    layered = load_ingest_configuration(cwd=project, user_config_file=user)
    selected = load_ingest_configuration(
        cwd=project,
        user_config_file=user,
        parser_policy="fallback",
    )

    assert layered.parser_policy == "rule"
    assert layered.inference_enabled is False
    assert layered.sources["parser_policy"] == f"environment:{environment}"
    assert layered.sources["inference_enabled"] == (
        f"project:{project / '.cognityx/ingest.toml'}"
    )
    assert selected.parser_policy == "fallback"
    assert selected.parser_backends == ("pymupdf", "docling", "basic")
    assert selected.inference_enabled is False
    assert selected.sources["parser_policy"] == "cli"
    assert selected.sources["parser_backends"] == f"environment:{environment}"
    assert selected.sources["inference_enabled"] == (
        f"project:{project / '.cognityx/ingest.toml'}"
    )


def test_explicit_ingest_file_is_highest_layer_and_shared_with_cogni(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    explicit = tmp_path / "explicit.toml"
    environment = tmp_path / "environment.toml"
    _write_config(project / ".cognityx/ingest.toml", policy="rule")
    _write_config(environment, backends=("pymupdf", "basic"))
    _write_config(explicit, policy="fallback", backends=("docling", "basic"))
    monkeypatch.setenv("COGNITYX_INGEST_CONFIG", str(environment))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user"))

    selected = load_ingest_configuration(config_file=explicit, cwd=project)
    cogni = Cogni.load(
        cwd=project,
        ingest_config=explicit,
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
    )
    report = selected.diagnostic_dict()

    assert selected == cogni.ingest_configuration
    assert selected.parser_policy == "fallback"
    assert report["master_config"]["path"] == str(explicit.resolve())
    assert report["master_config"]["selected_by"] == "explicit"
    assert [layer["selected_by"] for layer in report["config_layers"]] == [
        "project",
        "environment",
        "explicit",
    ]
    assert (
        report["master_config"]["sha256"]
        == __import__("hashlib").sha256(explicit.read_bytes()).hexdigest()
    )


def test_aggregate_config_ingest_is_static_and_missing_file_is_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    explicit = tmp_path / "ingest.toml"
    _write_config(explicit, policy="compare", backends=("basic",))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user"))
    monkeypatch.setattr(
        "cognityx.client.Cogni.load",
        lambda **_kwargs: pytest.fail("configuration inspection loaded Cogni"),
    )

    assert (
        main(
            [
                "config",
                "show",
                "--component",
                "ingest",
                "--ingest-config",
                str(explicit),
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["component"] == "ingest"
    assert shown["master_config"]["path"] == str(explicit.resolve())

    assert (
        main(
            [
                "config",
                "validate",
                "--component",
                "ingest",
                "--ingest-config",
                str(tmp_path / "missing"),
            ]
        )
        == 2
    )
    invalid = json.loads(capsys.readouterr().out)
    assert invalid["valid"] is False


def test_aggregate_config_all_keeps_owner_reports_and_actual_root_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user"))
    for name in (
        "COGNITYX_CONTEXT_FILE",
        "COGNITYX_INGEST_CONFIG",
        "COGNITYX_STORAGE_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "cognityx.client.Cogni.load",
        lambda **_kwargs: pytest.fail("configuration inspection loaded Cogni"),
    )
    storage_root = tmp_path / "storage"

    assert (
        main(
            [
                "config",
                "show",
                "--component",
                "all",
                "--storage-root",
                str(storage_root),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert report["component"] == "sdk"
    assert set(report["dependencies"]) == {"context", "ingest", "storage"}
    storage = report["dependencies"]["storage"]
    assert storage["overrides"][0]["previous"] == str(
        StorageConfig.built_in().profiles["local-main"].options["root"]
    )
    assert storage["overrides"][0]["effective"] == str(storage_root)
    assert storage["field_sources"][storage["overrides"][0]["key"]] == (
        "--storage-root"
    )


def test_ingest_config_alias_statically_validates_bounded_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user"))
    bounded = tmp_path / "bounded.toml"
    bounded.write_text('[inference]\nmodel="model-a"\n', encoding="utf-8")

    assert main(["ingest-config", "show", "--inference-config", str(bounded)]) == 0
    shown = json.loads(capsys.readouterr().out)
    selected = shown["runtime_selections"]["bounded_inference"]
    assert selected["path"] == str(bounded.resolve())
    assert (
        selected["sha256"]
        == __import__("hashlib").sha256(bounded.read_bytes()).hexdigest()
    )

    malformed = tmp_path / "malformed.toml"
    malformed.write_text("[inference", encoding="utf-8")
    assert (
        main(["ingest-config", "validate", "--inference-config", str(malformed)]) == 2
    )
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_project_configuration_is_discovered_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    config = project / ".cognityx/ingest.toml"
    _write_config(
        config,
        policy="compare",
        backends=("pymupdf", "docling", "basic"),
        inference=False,
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user-config"))

    selected = load_ingest_configuration(cwd=project)

    assert selected.parser_policy == "compare"
    assert selected.parser_backends == ("pymupdf", "docling", "basic")
    assert selected.inference_enabled is False
    assert set(selected.sources.values()) == {f"project:{config}"}


def test_cli_override_and_show_report_effective_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_config(
        tmp_path / ".cognityx/ingest.toml",
        policy="compare",
        backends=("pymupdf", "docling", "basic"),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user-config"))

    assert (
        main(
            [
                "ingest-config",
                "show",
                "--parser-policy",
                "fixed",
                "--parser-backend",
                "basic",
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)

    assert shown["ingest"]["parser_policy"] == "fixed"
    assert shown["ingest"]["parser_backends"] == ["basic"]
    assert shown["sources"]["parser_policy"] == "cli"
    assert shown["sources"]["parser_backends"] == "cli"
    assert "config" not in shown["ingest"]["inference"]
    assert shown["ingest"]["routing"] == {
        "adaptive_mode": "deterministic",
        "classification": "planning-only",
        "execution_active": False,
        "execution_control": "parser_policy",
    }
    assert shown["sources"]["routing.adaptive_mode"] == ("derived:ingest.parser_policy")


@pytest.mark.parametrize(
    "content,match",
    [
        ('[ingest]\nparser_policy = "invented"\n', "parser_policy"),
        (
            '[ingest]\nparser_backends = ["pymupdf", "unknown"]\n',
            "parser_backends",
        ),
    ],
)
def test_invalid_policy_or_backend_is_rejected(
    tmp_path: Path, content: str, match: str
) -> None:
    config = tmp_path / ".cognityx/ingest.toml"
    config.parent.mkdir(parents=True)
    config.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        load_ingest_configuration(cwd=tmp_path)


def test_inference_disabled_prevents_environment_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(
        tmp_path / ".cognityx/ingest.toml",
        policy="compare",
        backends=("basic",),
        inference=False,
    )
    monkeypatch.setenv(
        "COGNITYX_INGEST_INFERENCE_CONFIG", str(tmp_path / "must-not-load.toml")
    )
    monkeypatch.setattr(
        "cognityx.client.load_resolution_config",
        lambda _path: pytest.fail("disabled inference configuration was loaded"),
    )
    cogni = Cogni.load(
        cwd=tmp_path,
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    assert cogni.ingest_configuration.inference_enabled is False
    assert cogni.ingest_service._resolver is None


def test_inference_enabled_requires_a_target_configuration(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path / ".cognityx/ingest.toml",
        policy="compare",
        backends=("basic",),
        inference=True,
    )
    cogni = Cogni.load(
        cwd=tmp_path,
        storage_runtime=StorageRuntime.from_config(
            StorageConfig.built_in(root=tmp_path / "storage")
        ),
        catalog_path=tmp_path / "catalog.sqlite3",
    )

    with pytest.raises(ValueError, match="no inference target"):
        cogni.ingest_service


def test_no_configuration_uses_safe_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user-config"))
    selected = load_ingest_configuration(cwd=tmp_path)

    assert selected.parser_policy == "fixed"
    assert selected.parser_backends == ("basic",)
    assert selected.inference_enabled is False
    assert set(selected.sources.values()) == {"built-in defaults"}


def test_validate_reports_valid_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path / ".cognityx/ingest.toml", policy="compare")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user-config"))

    assert main(["ingest-config", "validate"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["valid"] is True
    assert payload["ingest"]["parser_policy"] == "compare"


@pytest.mark.parametrize(
    "content,match",
    (
        ('[ingest]\nrouting_mode = "deterministic"\n', "routing_mode"),
        ('[ingest.routing]\nmode = "deterministic"\n', "routing"),
        ('[ingest]\nparser_backends = ["basic", "basic"]\n', "duplicates"),
        ("[ingest]\nparser_backends = []\n", "non-empty"),
        ('[secrets]\ntoken = "must-not-appear"\n', "secrets"),
    ),
)
def test_unknown_no_op_and_invalid_settings_fail_closed(
    tmp_path: Path, content: str, match: str
) -> None:
    config = tmp_path / ".cognityx/ingest.toml"
    config.parent.mkdir(parents=True)
    config.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        load_ingest_configuration(cwd=tmp_path)


def test_config_show_is_secret_free_and_validation_starts_no_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path / ".cognityx/ingest.toml", policy="fixed")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-user-config"))
    monkeypatch.setenv("COGNITYX_API_TOKEN", "top-secret-value")
    monkeypatch.setattr(
        "cognityx.client.Cogni.load",
        lambda **_kwargs: pytest.fail("configuration validation loaded Cogni"),
    )

    assert main(["ingest-config", "validate"]) == 0
    output = capsys.readouterr().out

    assert "top-secret-value" not in output
    assert json.loads(output)["valid"] is True
