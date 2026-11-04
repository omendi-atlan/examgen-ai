"""EXAMGEN AI command line interface.

The CLI drives the same services as the HTTP API, so a complete examination can
be produced and inspected without a browser: create a subject workspace, ingest
only that subject's coursework, classify it, approve visuals, generate and
moderate an examination, then emit both PDF deliverables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import init_db, session_scope
from .models import Examination, ExaminationBlueprint, SubjectWorkspace, User
from .security import hash_password
from .services import examination as exam_service
from .services import workspace as ws


def _out(message: str = "") -> None:
    print(message)


def _resolve_workspace(db, ref: str) -> SubjectWorkspace:
    """Find a workspace by id, code or case-insensitive name."""
    found = db.get(SubjectWorkspace, ref)
    if found:
        return found
    found = db.query(SubjectWorkspace).filter(
        (SubjectWorkspace.code == ref) | (SubjectWorkspace.name.ilike(ref))).first()
    if not found:
        raise SystemExit(f"No subject workspace matches {ref!r}. Try `examgen subjects`.")
    return found


def _resolve_examination(db, ref: str) -> Examination:
    found = db.get(Examination, ref)
    if not found:
        found = db.query(Examination).filter(Examination.title.ilike(ref)).first()
    if not found:
        raise SystemExit(f"No examination matches {ref!r}. Try `examgen examinations <subject>`.")
    return found


def cmd_init_db(_args: argparse.Namespace) -> int:
    init_db()
    _out("Database initialised.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api.app import create_app

    init_db()
    if args.reload:
        uvicorn.run("examgen.api.app:create_app", host=args.host, port=args.port,
                    reload=True, factory=True)
    else:
        uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def cmd_user_create(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        if db.query(User).filter(User.email == args.email).first():
            raise SystemExit(f"A user with email {args.email!r} already exists.")
        user = User(email=args.email, display_name=args.name,
                    password_hash=hash_password(args.password), role=args.role)
        db.add(user)
        db.flush()
        _out(f"Created user {user.email} ({user.role}) id={user.id}")
    return 0


def cmd_subject_create(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        owner = db.query(User).filter(User.email == args.owner).first()
        if not owner:
            raise SystemExit(f"No user {args.owner!r}. Create one with `examgen user-create`.")
        workspace = SubjectWorkspace(
            owner_id=owner.id, name=args.name, code=args.code, module=args.module,
            institution=args.institution, qualification=args.qualification,
            description=args.description or "")
        db.add(workspace)
        db.flush()
        ws.audit(db, workspace.id, owner.id, "workspace.created", "workspace",
                 workspace.id, {"name": workspace.name})
        _out(f"Created subject workspace {workspace.name!r} id={workspace.id}")
    return 0


def cmd_subjects(_args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspaces = db.query(SubjectWorkspace).order_by(SubjectWorkspace.name).all()
        if not workspaces:
            _out("No subject workspaces yet.")
            return 0
        for workspace in workspaces:
            summary = ws.workspace_summary(db, workspace)
            _out(f"{workspace.id}  {workspace.name}  [{workspace.code or 'no code'}]  "
                 f"documents={summary['document_count']}  topics={summary['topic_count']}  "
                 f"examinations={summary['examination_count']}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        for raw in args.paths:
            path = Path(raw)
            if not path.is_file():
                raise SystemExit(f"Not a file: {path}")
            document = ws.store_upload(db, workspace, path.name, path.read_bytes(),
                                       content_type="", declared_kind=args.kind)
            ws.process_document(db, document)
            _out(f"Ingested {path.name} -> {document.id} "
                 f"({document.extracted_chars} chars, {document.processing_status})")
        report = ws.reclassify(db, workspace)
        _out(f"Classification verdict: {report.verdict} — "
             f"{len(report.adequate)} adequate, {len(report.partial)} partial, "
             f"{len(report.missing)} missing")
        for gap in report.missing:
            _out(f"  missing topic: {gap}")
        for gap in report.missing_outcomes:
            _out(f"  missing outcome: {gap}")
        for conflict in report.conflicts:
            _out(f"  conflict: {conflict}")
        for item in report.insufficient_types:
            _out(f"  insufficient for: {item}")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        report = ws.reclassify(db, workspace)
        _out(json.dumps(report.model_dump() if hasattr(report, "model_dump")
                        else vars(report), indent=2, default=str))
    return 0


def cmd_topics(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        for topic in workspace.topics:
            _out(f"{topic.id}  {topic.name}  coverage={topic.coverage}  "
                 f"visual={topic.needs_visual}")
            for subtopic in topic.subtopics:
                _out(f"    - {subtopic.name}")
    return 0


def cmd_visuals_propose(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        assets = ws.propose_visuals(db, workspace)
        if not assets:
            _out("No visual requirements detected — no assets were fabricated.")
        for asset in assets:
            _out(f"Proposed {asset.id}  {asset.title}  ({asset.diagram_type}, {asset.requirement})")
    return 0


def cmd_visuals_list(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        if not workspace.visuals:
            _out("No visual assets. Run `examgen visuals-propose <subject>` first.")
        for asset in workspace.visuals:
            _out(f"{asset.id}  v{asset.version}  {asset.status:9}  "
                 f"{asset.diagram_type:24}  {asset.title}")
    return 0


def cmd_visuals_decide(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        approve = args.decision == "approve"
        matched = [a for a in workspace.visuals if not args.visual or a.id == args.visual]
        if not matched:
            raise SystemExit("No matching visual assets.")
        for asset in matched:
            ws.approve_visual(db, asset, approve, workspace.owner_id)
            _out(f"{'Approved' if approve else 'Rejected'} {asset.id} {asset.title}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        blueprint = ExaminationBlueprint(
            workspace_id=workspace.id, title=args.title,
            duration_minutes=args.duration, total_marks=args.marks,
            question_count=args.questions, difficulty=args.difficulty)
        db.add(blueprint)
        db.flush()
        validation = exam_service.validate_blueprint(db, workspace, blueprint)
        if not validation["valid"]:
            _out("Blueprint is not valid:")
            for issue in validation["issues"]:
                _out(f"  - {issue}")
            raise SystemExit(1)
        examination = exam_service.generate_examination(
            db, workspace, blueprint, mode=args.mode, user_id=workspace.owner_id)
        _out(f"Generated examination {examination.id} v{examination.version} "
             f"status={examination.status} moderation={examination.moderation_status} "
             f"questions={len(examination.question_snapshot or [])}")
        for finding in (examination.moderation_findings or []):
            _out(f"  [{finding.get('severity')}] {finding.get('message')}")
        _out(f"EXAMINATION_ID={examination.id}")
    return 0


def cmd_examinations(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        if not workspace.examinations:
            _out("No examinations yet.")
        for exam in workspace.examinations:
            _out(f"{exam.id}  v{exam.version}  {exam.status:9}  "
                 f"{exam.moderation_status:15}  "
                 f"{len(exam.question_snapshot or [])}q  {exam.title}")
    return 0


def cmd_moderate(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        examination = _resolve_examination(db, args.examination)
        result = exam_service.remoderate(db, examination)
        _out(f"Moderation status: {result.status}")
        for finding in result.findings:
            _out(f"  [{finding.severity}] {finding.code}: {finding.message}")
    return 0


def cmd_questions(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as db:
        examination = _resolve_examination(db, args.examination)
        questions = examination.question_snapshot or []
        if not questions:
            _out("This examination has no questions recorded.")
        for position, snapshot in enumerate(questions, start=1):
            _out(f"Q{snapshot.get('ordinal') or position} [{snapshot.get('qtype')} / "
                 f"{snapshot.get('difficulty')} / {snapshot.get('bloom')}] "
                 f"{snapshot.get('marks')} marks")
            _out(f"    {str(snapshot.get('prompt', ''))[:300]}")
            if args.answers:
                _out(f"    ANSWER: {snapshot.get('expected_answer', '')}")
                _out(f"    RUBRIC: {json.dumps(snapshot.get('rubrics', []))}")
    return 0


def _deliverables(args: argparse.Namespace, only: str | None) -> int:
    init_db()
    with session_scope() as db:
        examination = _resolve_examination(db, args.examination)
        records = exam_service.generate_deliverables(db, examination)
        for kind, record in records.items():
            if only and kind != only:
                continue
            _out(f"{kind}: {record['path']} (v{record['version']})")
    return 0


def cmd_analytics(args: argparse.Namespace) -> int:
    init_db()
    from .services import analytics as analytics_service

    with session_scope() as db:
        workspace = _resolve_workspace(db, args.subject)
        _out(json.dumps(analytics_service.analyse_workspace(db, workspace.id),
                        indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="examgen",
                                     description="EXAMGEN AI academic examination platform")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the web application")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    sub.add_parser("init-db", help="Create database tables").set_defaults(func=cmd_init_db)

    user = sub.add_parser("user-create", help="Create a user account")
    user.add_argument("--email", required=True)
    user.add_argument("--password", required=True)
    user.add_argument("--name", default="")
    user.add_argument("--role", default="student", choices=["student", "lecturer", "admin"])
    user.set_defaults(func=cmd_user_create)

    subject = sub.add_parser("subject-create", help="Create an isolated subject workspace")
    subject.add_argument("--owner", required=True, help="Owner email")
    subject.add_argument("--name", required=True)
    subject.add_argument("--code", default="")
    subject.add_argument("--module", default="")
    subject.add_argument("--institution", default="")
    subject.add_argument("--qualification", default="")
    subject.add_argument("--description", default="")
    subject.set_defaults(func=cmd_subject_create)

    sub.add_parser("subjects", help="List subject workspaces").set_defaults(func=cmd_subjects)

    ingest = sub.add_parser("ingest", help="Upload and process coursework for one subject")
    ingest.add_argument("subject", help="Workspace id, code or name")
    ingest.add_argument("paths", nargs="+", help="Files to ingest")
    ingest.add_argument("--kind", default="coursework",
                        choices=["coursework", "previous_assessment", "memorandum",
                                 "study_guide", "image"])
    ingest.set_defaults(func=cmd_ingest)

    classify = sub.add_parser("classify", help="Classify content into topics and outcomes")
    classify.add_argument("subject")
    classify.set_defaults(func=cmd_classify)

    topics = sub.add_parser("topics", help="List topics and subtopics")
    topics.add_argument("subject")
    topics.set_defaults(func=cmd_topics)

    propose = sub.add_parser("visuals-propose", help="Assess and construct required visuals")
    propose.add_argument("subject")
    propose.set_defaults(func=cmd_visuals_propose)

    vlist = sub.add_parser("visuals", help="List visual assets")
    vlist.add_argument("subject")
    vlist.set_defaults(func=cmd_visuals_list)

    decide = sub.add_parser("visuals-decide", help="Approve or reject visual assets")
    decide.add_argument("subject")
    decide.add_argument("decision", choices=["approve", "reject"])
    decide.add_argument("--visual", default="", help="Single asset id (default: all)")
    decide.set_defaults(func=cmd_visuals_decide)

    generate = sub.add_parser("generate", help="Generate and moderate an examination")
    generate.add_argument("subject")
    generate.add_argument("--title", required=True)
    generate.add_argument("--duration", type=int, default=120)
    generate.add_argument("--marks", type=int, default=100)
    generate.add_argument("--questions", type=int, default=12)
    generate.add_argument("--difficulty", default="intermediate")
    generate.add_argument("--mode", default="practice", choices=["practice", "formal"])
    generate.set_defaults(func=cmd_generate)

    exams = sub.add_parser("examinations", help="List examinations for a subject")
    exams.add_argument("subject")
    exams.set_defaults(func=cmd_examinations)

    moderate = sub.add_parser("moderate", help="Re-run moderation on an examination")
    moderate.add_argument("examination")
    moderate.set_defaults(func=cmd_moderate)

    questions = sub.add_parser("questions", help="List examination questions")
    questions.add_argument("examination")
    questions.add_argument("--answers", action="store_true", help="Include answer keys")
    questions.set_defaults(func=cmd_questions)

    memo = sub.add_parser("memorandum", help="Generate the memorandum PDF")
    memo.add_argument("examination")
    memo.set_defaults(func=lambda a: _deliverables(a, "memorandum"))

    mastery = sub.add_parser("mastery", help="Generate the subject mastery PDF")
    mastery.add_argument("examination")
    mastery.set_defaults(func=lambda a: _deliverables(a, "mastery_guide"))

    deliverables = sub.add_parser("deliverables", help="Generate both PDF deliverables")
    deliverables.add_argument("examination")
    deliverables.set_defaults(func=lambda a: _deliverables(a, None))

    analytics = sub.add_parser("analytics", help="Show performance analytics for a subject")
    analytics.add_argument("subject")
    analytics.set_defaults(func=cmd_analytics)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
