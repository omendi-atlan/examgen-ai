"""Automated marking.

Objective question types are marked **deterministically** against the verified
answer key. Extended responses are marked against explicit rubrics; the
deterministic marker scores each criterion from evidence in the response and
always records a defensible rationale. Anything the marker cannot score
confidently is flagged ``needs_human_review`` rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Question, QuestionType
from . import textutil

OBJECTIVE_TYPES = {
    QuestionType.FILL_BLANK.value,
    QuestionType.SINGLE_CHOICE.value,
    QuestionType.MULTIPLE_CHOICE.value,
    QuestionType.MATCHING.value,
    QuestionType.NUMERICAL.value,
    QuestionType.ORDERING.value,
}

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _normalise(text: str) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"[^\w\s\.\-+]", "", text)
    return re.sub(r"\s+", " ", text)


@dataclass
class MarkResult:
    awarded: float
    max_marks: float
    method: str
    rationale: str
    needs_human_review: bool = False
    breakdown: list = field(default_factory=list)


def _key(question: Question) -> dict:
    return (question.answer_key.correct if question.answer_key else {}) or {}


def mark(question: Question, answer: dict) -> MarkResult:
    qtype = question.qtype
    marks = float(question.marks)
    key = _key(question)
    if qtype in OBJECTIVE_TYPES:
        return _mark_objective(question, answer, key, marks)
    return _mark_rubric(question, answer, marks)


def _mark_objective(question: Question, answer: dict, key: dict, marks: float) -> MarkResult:
    qtype = question.qtype
    given = answer.get("value", answer)

    if qtype == QuestionType.FILL_BLANK.value:
        expected = key.get("text") or question.expected_answer
        accepted = {_normalise(expected)} | {
            _normalise(a) for a in (question.acceptable_alternatives or [])}
        got = _normalise(given if isinstance(given, str) else str(given))
        correct = got in accepted or (
            got and any(a and (a in got or got in a) for a in accepted if len(a) > 3))
        return MarkResult(
            awarded=marks if correct else 0.0, max_marks=marks, method="objective",
            rationale=(f"Response “{given}” matches the keyed answer “{expected}”."
                       if correct else
                       f"Response “{given}” does not match the keyed answer “{expected}”."),
            breakdown=[{"criterion": "Exact/keyed match", "awarded": marks if correct else 0.0,
                        "max": marks}],
        )

    if qtype == QuestionType.SINGLE_CHOICE.value:
        expected = key.get("text", question.expected_answer)
        index = answer.get("index")
        correct_index = key.get("index")
        if correct_index is None and question.options:
            correct_index = question.options.index(expected) if expected in question.options else None
        correct = False
        if index is not None and correct_index is not None:
            correct = int(index) == int(correct_index)
        else:
            correct = _normalise(given) == _normalise(expected)
        return MarkResult(
            awarded=marks if correct else 0.0, max_marks=marks, method="objective",
            rationale=(f"Selected the keyed option. Correct answer: {expected}"
                       if correct else f"Incorrect option selected. Correct answer: {expected}"),
            breakdown=[{"criterion": "Correct option", "awarded": marks if correct else 0.0,
                        "max": marks}],
        )

    if qtype == QuestionType.MULTIPLE_CHOICE.value:
        correct_set = {_normalise(c) for c in key.get("correct", question.payload.get("correct", []))}
        selected = answer.get("selected")
        if selected is None:
            selected = [given] if isinstance(given, str) else list(given or [])
        selected_set = {_normalise(s) for s in selected}
        if not correct_set:
            return MarkResult(0.0, marks, "objective",
                              "No answer key available for this question.", True)
        hits = len(selected_set & correct_set)
        wrong = len(selected_set - correct_set)
        # All-or-nothing: any wrong selection cancels credit for correctness.
        awarded = marks if selected_set == correct_set else 0.0
        rationale = (f"Selected {hits} of {len(correct_set)} correct options"
                     + (f" with {wrong} incorrect selection(s)" if wrong else "")
                     + ("; exact match awarded full marks." if awarded else "; full marks require all and only the correct options."))
        return MarkResult(
            awarded=awarded, max_marks=marks, method="objective", rationale=rationale,
            breakdown=[{"criterion": "Correct option set", "awarded": awarded, "max": marks}],
        )

    if qtype == QuestionType.MATCHING.value:
        items = question.payload.get("items", [])
        given_map = answer.get("matches") or {}
        if not items:
            return MarkResult(0.0, marks, "objective", "No matching items defined.", True)
        per = marks / len(items)
        awarded = 0.0
        breakdown = []
        for item in items:
            prompt = item.get("prompt")
            expected = _normalise(item.get("answer", ""))
            got = _normalise(given_map.get(prompt, answer.get(prompt, "")))
            ok = bool(got) and got == expected
            awarded += per if ok else 0.0
            breakdown.append({"criterion": prompt, "awarded": round(per if ok else 0.0, 2),
                              "max": round(per, 2)})
        return MarkResult(
            awarded=round(awarded, 2), max_marks=marks, method="objective",
            rationale=f"{sum(1 for b in breakdown if b['awarded'])} of {len(items)} pairs matched correctly.",
            breakdown=breakdown,
        )

    if qtype == QuestionType.NUMERICAL.value:
        expected_raw = key.get("value", question.expected_answer)
        tolerance = float(key.get("tolerance", 0.0) or 0.0)
        try:
            expected = float(str(expected_raw).replace(",", ""))
        except (TypeError, ValueError):
            return MarkResult(0.0, marks, "objective",
                              "Answer key is not numeric; human review required.", True)
        numbers = _NUM_RE.findall(str(given))
        if not numbers:
            return MarkResult(0.0, marks, "objective",
                              f"No numeric value supplied. Expected {expected}.", False)
        got = float(numbers[0])
        ok = abs(got - expected) <= tolerance
        return MarkResult(
            awarded=marks if ok else 0.0, max_marks=marks, method="objective",
            rationale=(f"Answer {got} is within tolerance ({tolerance}) of the keyed value {expected}."
                       if ok else f"Answer {got} differs from the keyed value {expected}."),
            breakdown=[{"criterion": "Numerical accuracy", "awarded": marks if ok else 0.0,
                        "max": marks}],
        )

    if qtype == QuestionType.ORDERING.value:
        correct = question.payload.get("correct_order", [])
        given_order = answer.get("order") or (given if isinstance(given, list) else [])
        if not correct:
            return MarkResult(0.0, marks, "objective", "No correct sequence defined.", True)
        per = marks / len(correct)
        awarded = sum(per for i, item in enumerate(given_order[:len(correct)])
                      if _normalise(item) == _normalise(correct[i]))
        return MarkResult(
            awarded=round(awarded, 2), max_marks=marks, method="objective",
            rationale=f"{sum(1 for i, item in enumerate(given_order[:len(correct)]) if _normalise(item) == _normalise(correct[i]))}"
                      f" of {len(correct)} positions correct.",
            breakdown=[{"criterion": f"Position {i + 1}", "max": round(per, 2),
                        "awarded": round(per, 2) if i < len(given_order) and
                        _normalise(given_order[i]) == _normalise(correct[i]) else 0.0}
                       for i in range(len(correct))],
        )

    return MarkResult(0.0, marks, "objective", "Unsupported objective type.", True)


def _evidence_score(response_text: str, expected: str) -> tuple[float, list[str]]:
    """Proportion of key concepts from the expected answer present in a response."""
    expected_terms = set(textutil.content_tokens(expected))
    if not expected_terms:
        return 0.0, []
    response_terms = set(textutil.content_tokens(response_text))
    matched = expected_terms & response_terms
    score = len(matched) / len(expected_terms)
    # Reward longer, structured responses modestly when they contain the concepts.
    if len(response_text.split()) > 40:
        score = min(1.0, score * 1.1)
    return score, sorted(matched)


def _mark_rubric(question: Question, answer: dict, marks: float) -> MarkResult:
    response_text = str(answer.get("value", answer.get("text", "")) or "").strip()
    rubrics = question.rubrics or []
    if not response_text:
        return MarkResult(0.0, marks, "rubric",
                          "No response was submitted for this question.",
                          breakdown=[{"criterion": r.criterion, "awarded": 0.0, "max": r.marks}
                                     for r in rubrics])

    expected = question.expected_answer or ""
    coverage, matched = _evidence_score(response_text, expected)
    response_words = len(response_text.split())
    expected_words = max(1, len(expected.split()))
    # A response must be reasonably developed before it can earn full credit.
    # Require the larger of eight words or 40% of the model answer, but never
    # more than the model answer itself — otherwise a short but exact answer
    # could never score full marks.
    required_words = max(min(8, expected_words), expected_words * 0.4)
    development = min(1.0, response_words / required_words)

    if not rubrics:
        awarded = round(marks * coverage * development, 2)
        return MarkResult(
            awarded=awarded, max_marks=marks, method="rubric",
            rationale=(f"Response covers {coverage:.0%} of the key concepts "
                       f"({', '.join(matched[:8]) or 'no key terms matched'}) and is "
                       f"{response_words} words against a {expected_words}-word model answer."),
            needs_human_review=coverage < 0.15 or development < 0.25,
            breakdown=[{"criterion": "Concept coverage", "awarded": awarded, "max": marks}],
        )

    total_rubric_marks = sum(r.marks for r in rubrics) or marks
    awarded = 0.0
    breakdown: list[dict] = []
    for rubric in rubrics:
        weight = rubric.marks / total_rubric_marks
        criterion_score = coverage * development
        if rubric.partial_credit:
            earned = round(rubric.marks * criterion_score, 2)
        else:
            earned = float(rubric.marks) if criterion_score >= 0.75 else 0.0
        earned = min(earned, float(rubric.marks))
        awarded += earned
        breakdown.append({"criterion": rubric.criterion, "awarded": earned,
                          "max": rubric.marks, "guidance": rubric.guidance})

    awarded = round(min(awarded, marks), 2)
    low_confidence = coverage < 0.15 or development < 0.25
    rationale = (
        f"Rubric marking: {coverage:.0%} conceptual coverage "
        f"({', '.join(matched[:8]) or 'no key terms matched'}); "
        f"response development {development:.0%} of the model answer "
        f"({response_words} vs {expected_words} words). "
        + ("Flagged for human review — insufficient evidence to mark confidently."
           if low_confidence else
           "Marked against the published rubric criteria.")
    )
    return MarkResult(
        awarded=awarded, max_marks=marks, method="rubric", rationale=rationale,
        needs_human_review=low_confidence, breakdown=breakdown,
    )


def is_objective(qtype: str) -> bool:
    return qtype in OBJECTIVE_TYPES
