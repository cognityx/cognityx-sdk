from __future__ import annotations

import sys
from types import ModuleType

import pytest

from cognityx.cli import main


@pytest.mark.parametrize(
    ("arguments", "forwarded"),
    [
        (["experiment", "validate", "research.yaml"], ["validate", "research.yaml"]),
        (
            ["experiment", "plan", "research.yaml", "--execution-id", "execution-1"],
            ["plan", "research.yaml", "--execution-id", "execution-1"],
        ),
        (
            ["experiment", "show-plan", "research.yaml"],
            ["show-plan", "research.yaml"],
        ),
        (
            [
                "experiment",
                "preflight",
                "research.yaml",
                "--storage-config",
                "storage.toml",
                "--results-repo",
                "results",
                "--push-results",
            ],
            [
                "preflight",
                "research.yaml",
                "--storage-config",
                "storage.toml",
                "--results-repo",
                "results",
                "--push-results",
            ],
        ),
        (
            [
                "experiment",
                "run",
                "research.yaml",
                "--resume",
                "--dry-run",
                "--storage-root",
                "research-storage",
                "--results-repo",
                "results",
            ],
            [
                "run",
                "research.yaml",
                "--resume",
                "--dry-run",
                "--storage-root",
                "research-storage",
                "--results-repo",
                "results",
            ],
        ),
        (
            [
                "experiment",
                "status",
                "execution-1",
                "--storage-root",
                "research-storage",
            ],
            [
                "status",
                "execution-1",
                "--storage-root",
                "research-storage",
            ],
        ),
        (
            [
                "experiment",
                "research-summary",
                "POLICY-H1",
                "--results-repo",
                "results",
            ],
            [
                "research-summary",
                "POLICY-H1",
                "--results-repo",
                "results",
            ],
        ),
        (
            [
                "experiment",
                "paper-material",
                "POLICY-RQ1",
                "--results-repo",
                "results",
            ],
            [
                "paper-material",
                "POLICY-RQ1",
                "--results-repo",
                "results",
            ],
        ),
    ],
)
def test_experiment_commands_delegate_without_loading_sdk_components(
    arguments,
    forwarded,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    calls: list[list[str]] = []
    package = ModuleType("cognityx_experiments")
    package.__path__ = []  # type: ignore[attr-defined]
    cli = ModuleType("cognityx_experiments.cli")

    def fake_main(values: list[str]) -> int:
        calls.append(values)
        return 0

    cli.main = fake_main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cognityx_experiments", package)
    monkeypatch.setitem(sys.modules, "cognityx_experiments.cli", cli)
    monkeypatch.setattr(
        "cognityx.cli._load",
        lambda _args: (_ for _ in ()).throw(AssertionError("SDK root loaded")),
    )

    assert main(arguments) == 0
    assert calls == [forwarded]
    assert capsys.readouterr().out == ""
