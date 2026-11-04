"""CLI acceptance tests.

The CLI must be able to drive the full academic workflow against real
persistence: create a subject workspace, ingest coursework, classify it,
construct and approve visuals, generate and moderate an examination, inspect
the question bank, and emit both PDF deliverables.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from examgen import cli
from examgen.db import session_scope
from examgen.models import AcademicDocument, Examination, SubjectWorkspace

from .conftest import make_text_document


@pytest.fixture()
def coursework(tmp_path: Path) -> Path:
    path = tmp_path / "module-notes.txt"
    path.write_bytes(make_text_document())
    return path


def test_cli_help_lists_workflow_commands(capsys):
    # No subcommand prints help and reports a non-zero status.
    assert cli.main([]) == 1
    assert "ingest" in capsys.readouterr().out


def test_cli_full_workflow(coursework, capsys):
    email = "cli-flow@example.com"

    assert cli.main(["user-create", "--email", email,
                     "--password", "cli-password-123", "--name", "CLI Flow"]) == 0
    capsys.readouterr()

    assert cli.main(["subject-create", "--owner", email,
                     "--name", "Algorithms CLI", "--code", "CS900"]) == 0
    assert "Created subject workspace" in capsys.readouterr().out

    with session_scope() as db:
        workspace = db.query(SubjectWorkspace).filter(
            SubjectWorkspace.code == "CS900").one()
        workspace_id = workspace.id

    # Ingest the coursework and classify it into topics.
    assert cli.main(["ingest", "CS900", str(coursework)]) == 0
    ingest_out = capsys.readouterr().out
    assert "Ingested" in ingest_out
    assert "Classification verdict" in ingest_out

    # Topics were derived from the coursework only.
    assert cli.main(["topics", "CS900"]) == 0
    assert "coverage=" in capsys.readouterr().out

    # Visual requirements are assessed; assets are constructed and approved.
    assert cli.main(["visuals-propose", "CS900"]) == 0
    proposed = capsys.readouterr().out
    assert "Proposed" in proposed or "No visual requirements detected" in proposed
    assert cli.main(["visuals-decide", "CS900", "approve"]) == 0
    capsys.readouterr()

    # Generate, moderate and publish an examination.
    assert cli.main(["generate", "CS900", "--title", "Algorithms CLI Exam",
                     "--questions", "10", "--marks", "80", "--duration", "90"]) == 0
    generated = capsys.readouterr().out
    assert "Generated examination" in generated
    assert "EXAMINATION_ID=" in generated
    examination_id = generated.split("EXAMINATION_ID=")[1].strip()

    with session_scope() as db:
        examination = db.get(Examination, examination_id)
        assert examination is not None
        assert examination.workspace_id == workspace_id
        assert examination.status == "published"
        assert examination.moderation_status in {"approved", "requires_review"}
        assert len(examination.question_snapshot) == 10

    # The question bank is inspectable, with answers available on request.
    assert cli.main(["questions", examination_id, "--answers"]) == 0
    questions_out = capsys.readouterr().out
    assert "ANSWER:" in questions_out
    assert "RUBRIC:" in questions_out

    # Both PDF deliverables are produced against the same examination version.
    assert cli.main(["deliverables", examination_id]) == 0
    deliverables_out = capsys.readouterr().out
    assert "memorandum:" in deliverables_out
    assert "mastery_guide:" in deliverables_out

    with session_scope() as db:
        examination = db.get(Examination, examination_id)
        memo = Path([p for p in examination.pdfs if p.kind == "memorandum"][0].path)
        guide = Path([p for p in examination.pdfs if p.kind == "mastery_guide"][0].path)
    assert memo.exists() and memo.stat().st_size > 2000
    assert guide.exists() and guide.stat().st_size > 2000
    assert f"v{examination.version}" in memo.name
    assert f"v{examination.version}" in guide.name


def test_cli_declared_kind_is_persisted(coursework, capsys):
    email = "cli-kind@example.com"
    cli.main(["user-create", "--email", email, "--password", "cli-password-123"])
    cli.main(["subject-create", "--owner", email, "--name", "Kind Subject", "--code", "KIND1"])
    capsys.readouterr()

    assert cli.main(["ingest", "KIND1", str(coursework),
                     "--kind", "previous_assessment"]) == 0
    capsys.readouterr()

    with session_scope() as db:
        workspace = db.query(SubjectWorkspace).filter(
            SubjectWorkspace.code == "KIND1").one()
        document = db.query(AcademicDocument).filter(
            AcademicDocument.workspace_id == workspace.id,
            AcademicDocument.filename == coursework.name).one()
        assert document.kind == "previous_assessment"


def test_cli_rejects_unknown_workspace(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["topics", "no-such-subject"])
    assert "No subject workspace matches" in str(exit_info.value)
