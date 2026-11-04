"""Student performance intelligence.

All analytics are derived from persisted attempts, responses and marking
records — never from assumptions. Where there is no evidence the classification
is explicitly ``not_assessed``.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Examination,
    ExaminationAttempt,
    LearningOutcome,
    MarkingRecord,
    MasteryLevel,
    Question,
    StudentResponse,
    Subtopic,
    Topic,
)

MASTERY_THRESHOLDS = [
    (0.0, MasteryLevel.NOT_ASSESSED),
    (0.40, MasteryLevel.REQUIRES_IMPROVEMENT),
    (0.55, MasteryLevel.DEVELOPING),
    (0.70, MasteryLevel.COMPETENT),
    (0.85, MasteryLevel.STRONG),
]


def classify_mastery(percentage: float | None) -> str:
    if percentage is None:
        return MasteryLevel.NOT_ASSESSED.value
    ratio = percentage / 100 if percentage > 1 else percentage
    level = MasteryLevel.REQUIRES_IMPROVEMENT.value
    for threshold, mastery in MASTERY_THRESHOLDS:
        if ratio >= threshold:
            level = mastery.value
    return level


def _question_index(db: Session, examination: Examination) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for q in examination.question_snapshot or []:
        index[q.get("question_id")] = q
    return index


def analyse_workspace(db: Session, workspace_id: str,
                      student_id: str | None = None) -> dict:
    attempts = list(db.scalars(
        select(ExaminationAttempt).where(
            ExaminationAttempt.workspace_id == workspace_id,
            ExaminationAttempt.status.in_(["submitted", "marked", "expired"]),
        ).order_by(ExaminationAttempt.started_at.asc())))
    if student_id:
        attempts = [a for a in attempts if a.student_id == student_id]

    topic_names = {t.id: t.name for t in db.scalars(
        select(Topic).where(Topic.workspace_id == workspace_id))}
    outcome_statements = {o.id: o.statement for o in db.scalars(
        select(LearningOutcome).where(LearningOutcome.workspace_id == workspace_id))}

    by_topic: dict[str, dict] = defaultdict(lambda: {"awarded": 0.0, "max": 0.0, "questions": 0})
    by_outcome: dict[str, dict] = defaultdict(lambda: {"awarded": 0.0, "max": 0.0, "questions": 0})
    by_difficulty: dict[str, dict] = defaultdict(lambda: {"awarded": 0.0, "max": 0.0, "questions": 0})
    by_bloom: dict[str, dict] = defaultdict(lambda: {"awarded": 0.0, "max": 0.0, "questions": 0})
    mistake_counter: dict[str, dict] = defaultdict(lambda: {"count": 0, "text": "", "topic": ""})
    history: list[dict] = []

    for attempt in attempts:
        examination = db.get(Examination, attempt.examination_id)
        if examination is None:
            continue
        qindex = _question_index(db, examination)
        markings = list(db.scalars(select(MarkingRecord).where(
            MarkingRecord.attempt_id == attempt.id)))
        for record in markings:
            question = qindex.get(record.question_id, {})
            topic_id = question.get("topic_id") or ""
            outcome_id = question.get("learning_outcome_id") or ""
            difficulty = question.get("difficulty", "unknown")
            bloom = question.get("bloom", "unknown")
            ratio = (record.awarded / record.max_marks) if record.max_marks else 0.0
            for bucket, key in ((by_topic, topic_id), (by_outcome, outcome_id),
                                (by_difficulty, difficulty), (by_bloom, bloom)):
                bucket[key]["awarded"] += record.awarded
                bucket[key]["max"] += record.max_marks
                bucket[key]["questions"] += 1
            if record.max_marks and ratio < 0.5:
                key = f"{topic_id}:{question.get('prompt', '')[:60]}"
                mistake_counter[key]["count"] += 1
                mistake_counter[key]["text"] = question.get("prompt", "")[:160]
                mistake_counter[key]["topic"] = topic_names.get(topic_id, "Unclassified")
        history.append({
            "attempt_id": attempt.id,
            "examination_id": attempt.examination_id,
            "title": examination.title,
            "version": examination.version,
            "mode": attempt.mode,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "score": attempt.score,
            "max_score": attempt.max_score,
            "percentage": attempt.percentage,
        })

    percentages = [a.percentage for a in attempts if a.percentage is not None]

    def _rate(bucket: dict[str, dict], name_lookup=None) -> list[dict]:
        out = []
        for key, value in bucket.items():
            if not key or value["max"] == 0:
                continue
            pct = round(value["awarded"] / value["max"] * 100, 2)
            label = name_lookup.get(key, key) if name_lookup else key
            out.append({
                "id": key,
                "name": label,
                "awarded": round(value["awarded"], 2),
                "max": round(value["max"], 2),
                "percentage": pct,
                "questions": value["questions"],
                "mastery": classify_mastery(pct),
            })
        return sorted(out, key=lambda x: x["percentage"])

    repeated = sorted(
        ({"key": k, **v} for k, v in mistake_counter.items() if v["count"] > 1),
        key=lambda x: -x["count"])[:10]

    overall_mastery = classify_mastery(
        sum(percentages) / len(percentages) if percentages else None)

    topic_rows = _rate(by_topic, topic_names)
    outcome_rows = _rate(by_outcome, outcome_statements)

    recommendations: list[str] = []
    for row in topic_rows[:3]:
        if row["percentage"] < 70:
            recommendations.append(
                f"Revise “{row['name']}” — currently at {row['percentage']}% "
                f"across {row['questions']} marked questions.")
    for mistake in repeated[:3]:
        recommendations.append(
            f"Repeated difficulty with a question in {mistake['topic']}: "
            f"attempted incorrectly {mistake['count']} times.")
    weak_difficulty = [r for r in _rate(by_difficulty) if r["percentage"] < 60]
    for row in weak_difficulty[:2]:
        recommendations.append(
            f"Practise {row['name']}-level questions; performance is {row['percentage']}%.")
    if not recommendations and percentages:
        recommendations.append(
            "Performance is consistent across assessed topics. Continue with "
            "higher-difficulty practice to consolidate mastery.")
    if not percentages:
        recommendations.append(
            "No marked attempts yet. Complete a practice examination to generate "
            "personalised revision recommendations.")

    return {
        "workspace_id": workspace_id,
        "attempts": len(attempts),
        "average_percentage": round(sum(percentages) / len(percentages), 2) if percentages else None,
        "by_topic": topic_rows,
        "by_outcome": outcome_rows,
        "by_difficulty": _rate(by_difficulty),
        "by_bloom": _rate(by_bloom),
        "repeated_mistakes": repeated,
        "mastery": {
            "overall": overall_mastery,
            "by_topic": {row["name"]: row["mastery"] for row in topic_rows},
        },
        "recommendations": recommendations,
        "history": history,
    }


def attempt_analytics(db: Session, attempt: ExaminationAttempt,
                      examination: Examination) -> dict:
    markings = list(db.scalars(select(MarkingRecord).where(
        MarkingRecord.attempt_id == attempt.id)))
    qindex = _question_index(db, examination)
    topic_names = {t.id: t.name for t in db.scalars(select(Topic).where(
        Topic.workspace_id == examination.workspace_id))}
    by_topic: dict[str, dict] = defaultdict(lambda: {"awarded": 0.0, "max": 0.0})
    for record in markings:
        question = qindex.get(record.question_id, {})
        topic = topic_names.get(question.get("topic_id", ""), "Unclassified")
        by_topic[topic]["awarded"] += record.awarded
        by_topic[topic]["max"] += record.max_marks
    topics = [
        {"name": name, "awarded": round(v["awarded"], 2), "max": round(v["max"], 2),
         "percentage": round(v["awarded"] / v["max"] * 100, 2) if v["max"] else 0.0,
         "mastery": classify_mastery(v["awarded"] / v["max"] * 100 if v["max"] else None)}
        for name, v in by_topic.items()
    ]
    return {
        "score": attempt.score,
        "max_score": attempt.max_score,
        "percentage": attempt.percentage,
        "mastery": classify_mastery(attempt.percentage),
        "by_topic": sorted(topics, key=lambda t: t["percentage"]),
        "needs_human_review": sum(1 for m in markings if m.needs_human_review),
    }
