from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from cognityx.cli import _watch_job, main
from cognityx.human import render_human


@pytest.mark.parametrize(
    "arguments",
    [
        ["storage", "locate", "storage://local-main/artifacts/report.json"],
        ["asset", "list"],
        ["bundle", "list"],
        ["ingest", "report.pdf"],
        ["ingest-config", "show"],
        ["config", "validate"],
        ["job", "events", "job-123"],
        ["run", "show", "run-123"],
        ["document", "show", "doc-123"],
        ["artifact", "available", "doc-123"],
        ["provenance", "resolve", "doc-123", "address-123"],
        ["cleanup", "blobs"],
        ["describe"],
        ["experiment", "plan", "research.yaml"],
    ],
)
def test_human_option_covers_each_structured_output_family_once(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls: list[object] = []

    def execute(args: object) -> dict[str, object]:
        calls.append(args)
        return {
            "id": "full-identifier-0123456789",
            "uri": "storage://local-main/artifacts/full/path.json",
        }

    monkeypatch.setattr("cognityx.cli._execute", execute)

    assert main([*arguments, "--human"]) == 0
    captured = capsys.readouterr()

    assert len(calls) == 1
    assert captured.err == ""
    assert "Id: full-identifier-0123456789" in captured.out
    assert "storage://local-main/artifacts/full/path.json" in captured.out
    assert "\x1b[" not in captured.out


def test_default_json_bytes_are_unchanged_and_human_uses_same_payload_once(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    payload = {"z_value": 7, "a_value": "complete"}
    calls = 0

    def execute(_args: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return dict(payload)

    monkeypatch.setattr("cognityx.cli._execute", execute)

    assert main(["describe"]) == 0
    assert (
        capsys.readouterr().out == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    assert calls == 1

    assert main(["describe", "--human"]) == 0
    assert capsys.readouterr().out == "Z value: 7\nA value: complete\n"
    assert calls == 2


def test_human_renderer_handles_records_nested_values_overrides_and_empty_lists() -> (
    None
):
    rendered = render_human(
        {
            "valid": True,
            "records": [
                {"id": "record-1", "state": "ready"},
                {"id": "record-2", "state": "done"},
            ],
            "nested": {"hash": "abcdef0123456789"},
            "overrides": [
                {
                    "key": "storage.root",
                    "previous": "/old",
                    "effective": "/new",
                    "source": "--storage-root",
                }
            ],
            "warnings": [],
        }
    )

    assert "Valid: true" in rendered
    assert "Id        State" in rendered
    assert "record-1  ready" in rendered
    assert "Hash: abcdef0123456789" in rendered
    assert "storage.root: /old -> /new (--storage-root)" in rendered
    assert "Warnings:\n  No records." in rendered


@pytest.mark.parametrize(
    ("content", "encoding", "displayed"),
    [
        (b"first line\nsecond line\n", "utf-8", "first line\nsecond line\n"),
        (b"\xff\x00\x01", "base64", "/wAB"),
    ],
)
def test_artifact_human_output_labels_encoding_and_preserves_full_content(
    content: bytes,
    encoding: str,
    displayed: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    reads: list[tuple[str, str]] = []

    class Artifacts:
        def read(self, document_id: str, name: str) -> bytes:
            reads.append((document_id, name))
            return content

    monkeypatch.setattr(
        "cognityx.cli._load",
        lambda _args: SimpleNamespace(artifacts=Artifacts()),
    )

    assert main(["artifact", "read", "doc-1", "document", "--human"]) == 0
    captured = capsys.readouterr()

    assert reads == [("doc-1", "document")]
    assert captured.err == ""
    assert captured.out.startswith(
        f"Artifact: document\nEncoding: {encoding}\nContent:\n"
    )
    assert displayed in captured.out


def test_json_and_human_preserve_safe_secret_references(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    payload = {
        "provider": "example",
        "credential_reference": "environment:PROVIDER_API_KEY",
        "valid": True,
    }
    monkeypatch.setattr("cognityx.cli._execute", lambda _args: dict(payload))

    assert main(["config", "show"]) == 0
    json_output = capsys.readouterr().out
    assert json.loads(json_output) == payload
    assert "super-secret-value" not in json_output

    assert main(["config", "show", "--human"]) == 0
    human_output = capsys.readouterr().out
    assert "Credential reference: environment:PROVIDER_API_KEY" in human_output
    assert "super-secret-value" not in human_output


def test_human_mode_keeps_error_channel_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def fail(_args: object) -> None:
        raise ValueError("bounded validation failed")

    monkeypatch.setattr("cognityx.cli._execute", fail)

    assert main(["describe", "--human"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "bounded validation failed\n"


@pytest.mark.parametrize("human", [False, True])
def test_job_watch_streams_each_event_without_changing_domain_calls(
    human: bool, capsys
) -> None:
    event = {"sequence": 4, "state": "completed", "job_id": "job-1"}

    class Manager:
        def __init__(self) -> None:
            self.events_calls = 0
            self.show_calls = 0

        def job_events(
            self, *_args: object, **_kwargs: object
        ) -> list[dict[str, object]]:
            self.events_calls += 1
            return [event]

        def show_job(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            self.show_calls += 1
            return {"job": {"state": "completed"}}

    manager = Manager()
    cogni = SimpleNamespace(new_execution=lambda: object(), ingest_manager=manager)

    _watch_job(cogni, "job-1", owner_id="owner-1", after=0, human=human)
    output = capsys.readouterr().out

    assert manager.events_calls == 1
    assert manager.show_calls == 1
    if human:
        assert output == "Sequence: 4\nState: completed\nJob id: job-1\n"
    else:
        assert output == json.dumps(event, sort_keys=True) + "\n"


def test_job_watch_human_events_are_explicitly_flushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = {"sequence": 1, "state": "completed"}
    writes: list[tuple[str, bool]] = []

    class Manager:
        def job_events(
            self, *_args: object, **_kwargs: object
        ) -> list[dict[str, object]]:
            return [event]

        def show_job(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {"job": {"state": "completed"}}

    def record_print(value: str, *, flush: bool) -> None:
        writes.append((value, flush))

    monkeypatch.setattr("builtins.print", record_print)
    cogni = SimpleNamespace(new_execution=lambda: object(), ingest_manager=Manager())

    _watch_job(cogni, "job-1", owner_id="owner-1", after=0, human=True)

    assert writes == [("Sequence: 1\nState: completed", True)]


@pytest.mark.parametrize("command", ["show-plan", "research-summary"])
def test_native_experiment_text_commands_do_not_accept_human(
    command: str, capsys
) -> None:
    arguments = ["experiment", command]
    if command == "show-plan":
        arguments.append("research.yaml")
    else:
        arguments.extend(("target", "--results-repo", "results"))

    with pytest.raises(SystemExit) as exc:
        main([*arguments, "--human"])

    assert exc.value.code == 2
    assert "unrecognized arguments: --human" in capsys.readouterr().err
