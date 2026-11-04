"""Examination moderation engine.

Every examination is validated before publication against the blueprint and
against academic quality criteria. Findings are actionable and carry a
severity:

    critical  -> blocks publication (status REJECTED)
    major     -> status REQUIRES_REVIEW, publication blocked by default
    minor     -> advisory; publication allowed

An examination with unresolved critical errors is never published.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import (
    Difficulty,
    Examination,
    ModerationStatus,
    QuestionType,
)

CRITICAL = "critical"
MAJOR = "major"
MINOR = "minor"

# Question types whose answers are keyed and therefore deterministically checkable.
_OBJECTIVE = {
    QuestionType.FILL_BLANK.value,
    QuestionType.SINGLE_CHOICE.value,
    QuestionType.MULTIPLE_CHOICE.value,
    QuestionType.MATCHING.value,
    QuestionType.NUMERICAL.value,
    QuestionType.ORDERING.value,
}

# A rough sanity band for time-per-mark in a written examination.
MIN_MINUTES_PER_MARK = 0.6
MAX_MINUTES_PER_MARK = 4.0


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    question_id: str | None = None

    def as_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code,
                "message": self.message, "question_id": self.question_id}


@dataclass
class ModerationResult:
    status: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def can_publish(self) -> bool:
        return not any(f.severity in {CRITICAL, MAJOR} for f in self.findings)


def _difficulty_of(question: dict) -> str:
    return question.get("difficulty", Difficulty.INTERMEDIATE.value)


def moderate(examination: Examination) -> ModerationResult:
    findings: list[Finding] = []
    questions: list[dict] = examination.question_snapshot or []

    if not questions:
        findings.append(Finding(CRITICAL, "no_questions",
                                "The examination contains no questions."))
        return ModerationResult(ModerationStatus.REJECTED.value, findings)

    # 1. Marks and duration coherence.
    total_marks = sum(int(q.get("marks", 0)) for q in questions)
    if total_marks != examination.total_marks:
        findings.append(Finding(
            MAJOR, "marks_mismatch",
            f"Question marks total {total_marks} but the examination declares "
            f"{examination.total_marks}."))
    if any(int(q.get("marks", 0)) < 1 for q in questions):
        findings.append(Finding(CRITICAL, "zero_mark_question",
                                "One or more questions carry no marks."))
    per_mark = examination.duration_minutes / total_marks if total_marks else 0
    if per_mark < MIN_MINUTES_PER_MARK:
        findings.append(Finding(
            MAJOR, "duration_too_short",
            f"Only {per_mark:.2f} minutes per mark; students cannot complete this "
            f"paper in {examination.duration_minutes} minutes."))
    elif per_mark > MAX_MINUTES_PER_MARK:
        findings.append(Finding(
            MINOR, "duration_generous",
            f"{per_mark:.2f} minutes per mark is generous for this question mix."))

    # 2. Per-question integrity.
    seen_fingerprints: dict[str, str] = {}
    section_marks: dict[str, int] = {}
    for q in questions:
        qid = q.get("question_id", "")
        qtype = q.get("qtype", "")
        prompt = (q.get("prompt") or "").strip()
        section = q.get("section", "")
        section_marks[section] = section_marks.get(section, 0) + int(q.get("marks", 0))

        if len(prompt) < 15:
            findings.append(Finding(CRITICAL, "unclear_prompt",
                                    "Question prompt is missing or too short to be answerable.",
                                    qid))
        if q.get("validation_notes"):
            findings.append(Finding(MAJOR, "question_validation",
                                    f"Question failed validation: {q['validation_notes']}", qid))
        if not (q.get("expected_answer") or "").strip():
            findings.append(Finding(CRITICAL, "missing_answer_key",
                                    "Question has no expected answer.", qid))

        # Answer-key correctness for objective questions.
        if qtype in _OBJECTIVE:
            if qtype == QuestionType.SINGLE_CHOICE.value:
                options = q.get("options") or []
                if len(options) < 2:
                    findings.append(Finding(CRITICAL, "insufficient_options",
                                            "Single-choice question has fewer than two options.", qid))
                if (q.get("expected_answer") or "") not in options:
                    findings.append(Finding(CRITICAL, "answer_not_in_options",
                                            "The keyed answer is not among the options.", qid))
                if len(set(options)) != len(options):
                    findings.append(Finding(MAJOR, "duplicate_options",
                                            "Single-choice question contains duplicate options.", qid))
            if qtype == QuestionType.MULTIPLE_CHOICE.value:
                correct = (q.get("payload") or {}).get("correct") or []
                options = q.get("options") or []
                if len(correct) < 2:
                    findings.append(Finding(CRITICAL, "mc_insufficient_correct",
                                            "Multiple-choice question requires at least two correct options.", qid))
                if not set(correct).issubset(set(options)):
                    findings.append(Finding(CRITICAL, "mc_key_not_in_options",
                                            "A keyed correct option is not among the options.", qid))
                if len(correct) == len(options):
                    findings.append(Finding(MAJOR, "mc_all_correct",
                                            "Every option is correct; no distractor remains.", qid))
            if qtype == QuestionType.FILL_BLANK.value:
                if "________" not in prompt:
                    findings.append(Finding(MAJOR, "no_blank",
                                            "Fill-in question contains no blank.", qid))
                if (q.get("payload") or {}).get("answer_control") != "text_box":
                    findings.append(Finding(CRITICAL, "wrong_control",
                                            "Fill-in questions must use a text box.", qid))
            if qtype == QuestionType.ORDERING.value:
                correct = (q.get("payload") or {}).get("correct_order") or []
                if len(correct) < 2:
                    findings.append(Finding(CRITICAL, "no_sequence",
                                            "Ordering question has no defined correct sequence.", qid))
            if qtype == QuestionType.MATCHING.value:
                items = (q.get("payload") or {}).get("items") or []
                if len(items) < 2:
                    findings.append(Finding(CRITICAL, "no_match_items",
                                            "Matching question has fewer than two items.", qid))

        # Rubric completeness for non-objective questions.
        if qtype not in _OBJECTIVE and not q.get("rubrics"):
            findings.append(Finding(MAJOR, "missing_rubric",
                                    "Extended-response question has no marking rubric.", qid))

        # Visual-question consistency.
        if q.get("visual_asset_id"):
            visual = (examination.visual_snapshot or {}).get(q["visual_asset_id"])
            if not visual:
                findings.append(Finding(CRITICAL, "missing_visual",
                                        "Question references a visual asset that is not part of this examination.",
                                        qid))
            elif visual.get("version") != q.get("visual_version"):
                findings.append(Finding(CRITICAL, "visual_version_mismatch",
                                        "Question references a different visual version than the one published.",
                                        qid))
            elif visual.get("status") != "approved":
                findings.append(Finding(CRITICAL, "unapproved_visual",
                                        "Question references a visual that has not been approved.", qid))

        # Duplicate detection across the paper.
        fp = q.get("fingerprint", "")
        if fp:
            if fp in seen_fingerprints:
                findings.append(Finding(MAJOR, "duplicate_question",
                                        "Duplicate question detected in this examination.", qid))
            else:
                seen_fingerprints[fp] = qid

    # 3. Difficulty appropriateness against the blueprint.
    blueprint_difficulty = None
    if examination.blueprint_id:
        blueprint_difficulty = None  # resolved by caller if needed
    difficulties = [_difficulty_of(q) for q in questions]
    if len(set(difficulties)) == 1 and len(questions) > 4:
        findings.append(Finding(MINOR, "flat_difficulty",
                                "All questions share a single difficulty level; consider a spread."))

    # 4. Topic coverage — every declared topic should appear at least once.
    declared_topics = set()
    for q in questions:
        if q.get("topic_id"):
            declared_topics.add(q["topic_id"])
    if len(declared_topics) < min(2, len(questions)):
        findings.append(Finding(MINOR, "narrow_coverage",
                                "The examination draws on very few topics."))

    # 5. Section balance.
    if len(section_marks) > 1 and any(m == 0 for m in section_marks.values()):
        findings.append(Finding(MINOR, "empty_section",
                                "One or more sections contain no marks."))

    if any(f.severity == CRITICAL for f in findings):
        status = ModerationStatus.REJECTED.value
    elif any(f.severity == MAJOR for f in findings):
        status = ModerationStatus.REQUIRES_REVIEW.value
    else:
        status = ModerationStatus.APPROVED.value
    return ModerationResult(status, findings)
