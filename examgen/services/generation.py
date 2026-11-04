"""Intelligent question generation.

Questions are generated from the selected workspace's own material only:
uploaded coursework, previously uploaded tests/examinations and existing
question-bank items. Every question records the exact source content it was
built from, so provenance is auditable and nothing is fabricated.

The generator is deterministic: the same workspace, blueprint and version
produce the same examination, which is required for version consistency between
the website, the memorandum and the mastery guide.

An optional LLM path (:mod:`examgen.services.llm`) may be enabled; it receives
only the workspace excerpts and must return the same schema. When it is
unavailable the deterministic engine is used, so the workflow never breaks.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field

from ..models import (
    BloomLevel,
    Difficulty,
    ExtractedContent,
    LearningOutcome,
    Provenance,
    QuestionType,
    Subtopic,
    Topic,
    VisualAsset,
    VisualRequirement,
)
from . import textutil

# Marks typically awarded per question type before blueprint normalisation.
DEFAULT_MARKS = {
    QuestionType.FILL_BLANK.value: 1,
    QuestionType.SINGLE_CHOICE.value: 2,
    QuestionType.MULTIPLE_CHOICE.value: 3,
    QuestionType.MATCHING.value: 4,
    QuestionType.NUMERICAL.value: 4,
    QuestionType.FORMULA.value: 4,
    QuestionType.ORDERING.value: 5,
    QuestionType.SHORT_ANSWER.value: 5,
    QuestionType.DIAGRAM_INTERPRETATION.value: 6,
    QuestionType.DIAGRAM_LABELLING.value: 6,
    QuestionType.EXTENDED_RESPONSE.value: 10,
    QuestionType.CASE_STUDY.value: 12,
    QuestionType.ESSAY.value: 20,
}

DIFFICULTY_WEIGHT = {
    Difficulty.BEGINNER.value: 0.2,
    Difficulty.BASIC.value: 0.35,
    Difficulty.INTERMEDIATE.value: 0.55,
    Difficulty.ADVANCED.value: 0.78,
    Difficulty.EXPERT.value: 1.0,
}

BLOOM_DIFFICULTY = {
    BloomLevel.REMEMBER.value: Difficulty.BEGINNER.value,
    BloomLevel.UNDERSTAND.value: Difficulty.BASIC.value,
    BloomLevel.APPLY.value: Difficulty.INTERMEDIATE.value,
    BloomLevel.ANALYSE.value: Difficulty.ADVANCED.value,
    BloomLevel.EVALUATE.value: Difficulty.ADVANCED.value,
    BloomLevel.CREATE.value: Difficulty.EXPERT.value,
}

DEFAULT_TYPE_MIX = {
    QuestionType.SINGLE_CHOICE.value: 0.18,
    QuestionType.MULTIPLE_CHOICE.value: 0.08,
    QuestionType.FILL_BLANK.value: 0.12,
    QuestionType.SHORT_ANSWER.value: 0.20,
    QuestionType.MATCHING.value: 0.08,
    QuestionType.NUMERICAL.value: 0.08,
    QuestionType.ORDERING.value: 0.06,
    QuestionType.EXTENDED_RESPONSE.value: 0.12,
    QuestionType.CASE_STUDY.value: 0.04,
    QuestionType.ESSAY.value: 0.04,
}

DEFAULT_DIFFICULTY_MIX = {
    Difficulty.BEGINNER.value: 0.15,
    Difficulty.BASIC.value: 0.25,
    Difficulty.INTERMEDIATE.value: 0.35,
    Difficulty.ADVANCED.value: 0.20,
    Difficulty.EXPERT.value: 0.05,
}

DEFAULT_BLOOM_MIX = {
    BloomLevel.REMEMBER.value: 0.15,
    BloomLevel.UNDERSTAND.value: 0.30,
    BloomLevel.APPLY.value: 0.25,
    BloomLevel.ANALYSE.value: 0.15,
    BloomLevel.EVALUATE.value: 0.10,
    BloomLevel.CREATE.value: 0.05,
}


@dataclass
class MaterialUnit:
    """A reusable piece of source material a question can be built from."""

    text: str
    kind: str
    topic_id: str | None
    subtopic_id: str | None
    outcome_id: str | None
    document_id: str | None
    content_id: str | None
    provenance: str
    bloom: str = BloomLevel.UNDERSTAND.value
    terms: list[str] = field(default_factory=list)
    numbers: list[float] = field(default_factory=list)


@dataclass
class QuestionDraft:
    qtype: str
    prompt: str
    marks: int
    difficulty: str
    bloom: str
    topic_id: str | None = None
    subtopic_id: str | None = None
    outcome_id: str | None = None
    instructions: str = ""
    options: list = field(default_factory=list)
    payload: dict = field(default_factory=dict)
    expected_answer: str = ""
    acceptable_alternatives: list = field(default_factory=list)
    explanation: str = ""
    common_errors: list = field(default_factory=list)
    provenance: str = Provenance.COURSEWORK.value
    source_document_ids: list = field(default_factory=list)
    source_content_ids: list = field(default_factory=list)
    visual_asset_id: str | None = None
    visual_version: int | None = None
    rubrics: list[dict] = field(default_factory=list)
    deterministic: bool = True
    validation_notes: str = ""

    def fingerprint(self) -> str:
        parts = [self.qtype, re.sub(r"\W+", " ", self.prompt.lower()).strip()]
        if self.options:
            parts.append("|".join(sorted(str(o).lower() for o in self.options)))
        if self.payload.get("items"):
            parts.append("|".join(sorted(
                str(i.get("prompt", i)) for i in self.payload["items"])))
        return hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Material extraction
# --------------------------------------------------------------------------

_DEFINITION_RE = re.compile(
    r"^(?P<term>[A-Z][A-Za-z0-9 \-]{2,50}?)\s+"
    r"(?:is|are|refers to|means|is defined as|can be defined as|denotes)\s+"
    r"(?P<body>.+)$", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_FORMULA_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^=\n]{1,80})")
_TERM_RE = re.compile(r"\b[A-Z][a-z]{3,}\b")


def _clean_prompt_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_material(topic: Topic, contents: list[ExtractedContent],
                   subtopics: list[Subtopic],
                   outcomes: list[LearningOutcome]) -> list[MaterialUnit]:
    """Turn raw extracted content into question-buildable material units."""
    units: list[MaterialUnit] = []
    sub_by_id = {s.id: s for s in subtopics}
    outcome_by_sub: dict[str, list[LearningOutcome]] = {}
    for outcome in outcomes:
        outcome_by_sub.setdefault(outcome.subtopic_id, []).append(outcome)

    for content in contents:
        if len(content.text.strip()) < 25:
            continue
        subtopic_id = None
        for sub in subtopics:
            if sub.name and sub.name.lower() in (content.heading or "").lower():
                subtopic_id = sub.id
                break
        outcome_id = None
        for outcome in outcome_by_sub.get(subtopic_id or "", []):
            if any(t in content.text.lower() for t in textutil.content_tokens(outcome.statement)[:3]):
                outcome_id = outcome.id
                break
        for sentence in textutil.sentences(content.text) or [content.text]:
            sentence = _clean_prompt_text(sentence)
            if len(sentence) < 30:
                continue
            bloom = textutil.bloom_for(sentence)
            units.append(MaterialUnit(
                text=sentence,
                kind=content.kind,
                topic_id=topic.id,
                subtopic_id=subtopic_id,
                outcome_id=outcome_id,
                document_id=content.document_id,
                content_id=content.id,
                provenance=content.provenance,
                bloom=bloom,
                terms=_TERM_RE.findall(sentence)[:8],
                numbers=[float(n) for n in _NUMBER_RE.findall(sentence)][:6],
            ))
    return units


def _definitions(units: list[MaterialUnit]) -> list[tuple[str, str, MaterialUnit]]:
    found: list[tuple[str, str, MaterialUnit]] = []
    seen: set[str] = set()
    for unit in units:
        match = _DEFINITION_RE.match(unit.text)
        if not match:
            continue
        term = match.group("term").strip()
        # Drop a leading article so "A tree is ..." yields the term "tree"
        # rather than "A tree", which would read badly in question stems.
        term = re.sub(r"^(?:a|an|the)\s+", "", term, flags=re.IGNORECASE).strip()
        body = match.group("body").strip()
        if len(term) < 3 or len(body) < 15 or term.lower() in seen:
            continue
        seen.add(term.lower())
        found.append((term, body, unit))
    return found


# --------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------

def _rubric_for(qtype: str, marks: int, expected: str) -> list[dict]:
    if qtype in {QuestionType.SINGLE_CHOICE.value, QuestionType.MULTIPLE_CHOICE.value,
                 QuestionType.FILL_BLANK.value, QuestionType.MATCHING.value,
                 QuestionType.NUMERICAL.value, QuestionType.ORDERING.value}:
        return [{"criterion": "Correct response against the verified answer key",
                 "marks": marks, "guidance": "Award full marks only for an exact/keyed match.",
                 "partial_credit": qtype == QuestionType.MATCHING.value}]
    base = [
        {"criterion": "Correct terminology used", "marks": max(1, marks // 4),
         "guidance": "Subject-specific terminology from the coursework.", "partial_credit": True},
        {"criterion": "Core concept accuracy", "marks": max(1, marks // 2),
         "guidance": f"Accurate statement of: {expected[:120]}", "partial_credit": True},
        {"criterion": "Application / reasoning", "marks": max(1, marks - (marks // 4) - (marks // 2)),
         "guidance": "Correct reasoning, structure and application to context.", "partial_credit": True},
    ]
    return base


def _gen_fill_blank(units: list[MaterialUnit], rng: random.Random) -> QuestionDraft | None:
    candidates = [u for u in units if 60 <= len(u.text) <= 260 and u.terms]
    if not candidates:
        return None
    unit = rng.choice(candidates)
    term = rng.choice(unit.terms)
    if term.lower() not in unit.text.lower():
        return None
    blanked = re.sub(rf"\b{re.escape(term)}\b", "________", unit.text, count=1)
    return QuestionDraft(
        qtype=QuestionType.FILL_BLANK.value,
        prompt=f"Complete the statement by filling in the blank:\n\n{blanked}",
        marks=DEFAULT_MARKS[QuestionType.FILL_BLANK.value],
        difficulty=BLOOM_DIFFICULTY[unit.bloom],
        bloom=unit.bloom,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        payload={"answer_control": "text_box"},
        expected_answer=term,
        acceptable_alternatives=[term.lower(), term.upper(), term.capitalize()],
        explanation=f"The missing term is “{term}”, taken directly from the source material.",
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.FILL_BLANK.value,
                            DEFAULT_MARKS[QuestionType.FILL_BLANK.value], term),
    )


def _gen_single_choice(units: list[MaterialUnit], all_definitions: list[tuple[str, str, MaterialUnit]],
                       rng: random.Random) -> QuestionDraft | None:
    if len(all_definitions) < 3:
        return None
    term, body, unit = rng.choice(all_definitions)
    distractors = [d[1] for d in all_definitions if d[0] != term]
    if len(distractors) < 2:
        other = [u.text for u in units if u.text != body and len(u.text) > 40]
        distractors = (distractors + other)[:3]
    if len(distractors) < 2:
        return None
    rng.shuffle(distractors)
    options = [body] + distractors[:3]
    rng.shuffle(options)
    correct_index = options.index(body)
    return QuestionDraft(
        qtype=QuestionType.SINGLE_CHOICE.value,
        prompt=f"Select the correct description of {term}.",
        marks=DEFAULT_MARKS[QuestionType.SINGLE_CHOICE.value],
        difficulty=BLOOM_DIFFICULTY[unit.bloom],
        bloom=unit.bloom,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        options=options,
        payload={"answer_control": "dropdown", "option_labels": ["A", "B", "C", "D"]},
        expected_answer=body,
        acceptable_alternatives=[str(correct_index)],
        explanation=f"{term} is correctly described as: {body}",
        common_errors=["Selecting a definition that belongs to a different concept.",
                       "Choosing a partially correct but incomplete description."],
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.SINGLE_CHOICE.value,
                            DEFAULT_MARKS[QuestionType.SINGLE_CHOICE.value], body),
    )


def _gen_multiple_choice(units: list[MaterialUnit], all_definitions: list[tuple[str, str, MaterialUnit]],
                         rng: random.Random) -> QuestionDraft | None:
    if len(all_definitions) < 4:
        return None
    chosen = rng.sample(all_definitions, min(4, len(all_definitions)))
    correct = [c[1] for c in chosen[:2]]
    distractors = [c[1] for c in chosen[2:]]
    if len(correct) < 2 or not distractors:
        return None
    term = chosen[0][0]
    options = correct + distractors
    rng.shuffle(options)
    unit = chosen[0][2]
    return QuestionDraft(
        qtype=QuestionType.MULTIPLE_CHOICE.value,
        prompt=("Select ALL statements that correctly apply to "
                f"{term}. More than one option may be correct."),
        marks=DEFAULT_MARKS[QuestionType.MULTIPLE_CHOICE.value],
        difficulty=BLOOM_DIFFICULTY[unit.bloom],
        bloom=unit.bloom,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        options=options,
        payload={"answer_control": "checkboxes", "correct": correct},
        expected_answer="; ".join(correct),
        acceptable_alternatives=[],
        explanation="Correct options: " + " | ".join(correct),
        common_errors=["Selecting only one correct option.", "Selecting a distractor that is plausible but unverified."],
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.MULTIPLE_CHOICE.value,
                            DEFAULT_MARKS[QuestionType.MULTIPLE_CHOICE.value], " | ".join(correct)),
    )


def _gen_matching(units: list[MaterialUnit], all_definitions: list[tuple[str, str, MaterialUnit]],
                  rng: random.Random, topic_name: str = "this topic") -> QuestionDraft | None:
    if len(all_definitions) < 3:
        return None
    chosen = rng.sample(all_definitions, min(4, len(all_definitions)))
    items = [{"prompt": c[0], "answer": c[1]} for c in chosen]
    options = [c[1] for c in chosen]
    rng.shuffle(options)
    unit = chosen[0][2]
    return QuestionDraft(
        qtype=QuestionType.MATCHING.value,
        prompt=(f"Match each term relating to {topic_name} in the left column to "
                f"its correct description."),
        marks=DEFAULT_MARKS[QuestionType.MATCHING.value],
        difficulty=BLOOM_DIFFICULTY[unit.bloom],
        bloom=unit.bloom,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        options=options,
        payload={"answer_control": "dropdown_per_item", "items": items},
        expected_answer="; ".join(f"{i['prompt']} -> {i['answer']}" for i in items),
        explanation="Each term maps to the description used in the coursework.",
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.MATCHING.value,
                            DEFAULT_MARKS[QuestionType.MATCHING.value], "term-description pairs"),
    )


def _gen_ordering(units: list[MaterialUnit], rng: random.Random,
                  topic_name: str = "this topic") -> QuestionDraft | None:
    candidates = [u for u in units
                  if re.search(r"\b(first|then|next|finally|step\s*\d)\b", u.text, re.IGNORECASE)]
    if not candidates:
        return None
    unit = rng.choice(candidates)
    parts = [p.strip() for p in re.split(r"\b(?:first|then|next|finally)\b|;|,", unit.text)
             if len(p.strip()) > 12]
    if len(parts) < 3:
        return None
    correct_order = parts[:5]
    shuffled = correct_order[:]
    rng.shuffle(shuffled)
    if shuffled == correct_order:
        shuffled = list(reversed(correct_order))
    return QuestionDraft(
        qtype=QuestionType.ORDERING.value,
        prompt=f"Place the following steps relating to {topic_name} in the correct order.",
        marks=DEFAULT_MARKS[QuestionType.ORDERING.value],
        difficulty=BLOOM_DIFFICULTY[unit.bloom],
        bloom=unit.bloom,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        options=shuffled,
        payload={"answer_control": "reorder", "correct_order": correct_order},
        expected_answer=" -> ".join(correct_order),
        explanation="The correct sequence as stated in the source material is: "
                    + " -> ".join(correct_order),
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.ORDERING.value,
                            DEFAULT_MARKS[QuestionType.ORDERING.value], "correct sequence"),
    )


def _gen_numerical(units: list[MaterialUnit], rng: random.Random) -> QuestionDraft | None:
    candidates = [u for u in units if u.numbers and textutil.has_numeric_content(u.text)]
    if not candidates:
        return None
    unit = rng.choice(candidates)
    value = unit.numbers[-1]
    return QuestionDraft(
        qtype=QuestionType.NUMERICAL.value,
        prompt=("Using the information below, state the required value.\n\n"
                f"{unit.text}\n\nProvide your answer as a number."),
        marks=DEFAULT_MARKS[QuestionType.NUMERICAL.value],
        difficulty=Difficulty.INTERMEDIATE.value,
        bloom=BloomLevel.APPLY.value,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        payload={"answer_control": "numeric_input"},
        expected_answer=str(value),
        acceptable_alternatives=[],
        explanation=f"The value stated in the source material is {value}.",
        common_errors=["Rounding incorrectly.", "Using the wrong unit.", "Omitting the sign."],
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.NUMERICAL.value,
                            DEFAULT_MARKS[QuestionType.NUMERICAL.value], str(value)),
    )


def _gen_formula(units: list[MaterialUnit], rng: random.Random) -> QuestionDraft | None:
    candidates = [u for u in units if u.kind == "formula" or _FORMULA_RE.search(u.text)]
    if not candidates:
        return None
    unit = rng.choice(candidates)
    match = _FORMULA_RE.search(unit.text)
    formula = match.group(0) if match else unit.text
    return QuestionDraft(
        qtype=QuestionType.FORMULA.value,
        prompt=("State the relationship or formula described below and identify each symbol.\n\n"
                f"{unit.text}"),
        marks=DEFAULT_MARKS[QuestionType.FORMULA.value],
        difficulty=Difficulty.INTERMEDIATE.value,
        bloom=BloomLevel.APPLY.value,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        payload={"answer_control": "structured_formula",
                 "symbols": sorted(set(re.findall(r"\b[A-Za-z]\b", formula)))},
        expected_answer=formula,
        explanation=f"The relevant relationship from the coursework is: {formula}",
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=[
            {"criterion": "Correct formula stated", "marks": DEFAULT_MARKS[QuestionType.FORMULA.value] - 1,
             "guidance": "All terms in the correct relationship.", "partial_credit": True},
            {"criterion": "Symbols correctly identified", "marks": 1,
             "guidance": "Each symbol named with its meaning and unit.", "partial_credit": True},
        ],
    )


def _gen_short_answer(units: list[MaterialUnit], all_definitions: list[tuple[str, str, MaterialUnit]],
                      rng: random.Random) -> QuestionDraft | None:
    if all_definitions:
        term, body, unit = rng.choice(all_definitions)
        prompt = f"Define {term} and state its significance in this subject."
        expected = body
    else:
        candidates = [u for u in units if 60 <= len(u.text) <= 400]
        if not candidates:
            return None
        unit = rng.choice(candidates)
        prompt = f"Briefly explain the following, using correct terminology:\n\n{unit.text}"
        expected = unit.text
    return QuestionDraft(
        qtype=QuestionType.SHORT_ANSWER.value,
        prompt=prompt,
        marks=DEFAULT_MARKS[QuestionType.SHORT_ANSWER.value],
        difficulty=BLOOM_DIFFICULTY[unit.bloom],
        bloom=unit.bloom,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        payload={"answer_control": "text_box"},
        expected_answer=expected,
        acceptable_alternatives=[],
        explanation=f"A strong answer includes: {expected[:300]}",
        common_errors=["Omitting the key terminology.", "Giving an example without a definition."],
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.SHORT_ANSWER.value,
                            DEFAULT_MARKS[QuestionType.SHORT_ANSWER.value], expected),
    )


def _gen_extended(units: list[MaterialUnit], topic_name: str, rng: random.Random) -> QuestionDraft | None:
    candidates = [u for u in units if len(u.text) >= 80]
    if not candidates:
        return None
    unit = rng.choice(candidates)
    prompt = (f"Discuss {topic_name} in detail. Your answer should demonstrate understanding "
              f"of the underlying concepts and use appropriate terminology.\n\n"
              f"Use the following as a starting point:\n{unit.text}")
    return QuestionDraft(
        qtype=QuestionType.EXTENDED_RESPONSE.value,
        prompt=prompt,
        marks=DEFAULT_MARKS[QuestionType.EXTENDED_RESPONSE.value],
        difficulty=Difficulty.ADVANCED.value,
        bloom=BloomLevel.ANALYSE.value,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        payload={"answer_control": "textarea"},
        expected_answer=unit.text,
        explanation="A high-scoring answer develops the concept systematically and cites specifics.",
        common_errors=["Listing points without linking them.", "Ignoring the command word."],
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=_rubric_for(QuestionType.EXTENDED_RESPONSE.value,
                            DEFAULT_MARKS[QuestionType.EXTENDED_RESPONSE.value], unit.text),
    )


def _gen_case_study(units: list[MaterialUnit], topic_name: str, rng: random.Random) -> QuestionDraft | None:
    candidates = [u for u in units if len(u.text) >= 80]
    if len(candidates) < 2:
        return None
    context = rng.choice(candidates)
    parts = rng.sample(candidates, min(3, len(candidates)))
    items = [{"prompt": f"({i + 1}) {p.text[:200]}", "answer": p.text[:200]}
             for i, p in enumerate(parts)]
    return QuestionDraft(
        qtype=QuestionType.CASE_STUDY.value,
        prompt=(f"Read the following scenario relating to {topic_name} and answer the questions "
                f"that follow.\n\nScenario:\n{context.text}"),
        marks=DEFAULT_MARKS[QuestionType.CASE_STUDY.value],
        difficulty=Difficulty.ADVANCED.value,
        bloom=BloomLevel.ANALYSE.value,
        topic_id=context.topic_id, subtopic_id=context.subtopic_id, outcome_id=context.outcome_id,
        payload={"answer_control": "scenario", "items": items},
        expected_answer="; ".join(i["answer"] for i in items),
        explanation="Apply the concepts from the scenario to each sub-question.",
        provenance=context.provenance,
        source_document_ids=[context.document_id] if context.document_id else [],
        source_content_ids=[context.content_id] if context.content_id else [],
        rubrics=_rubric_for(QuestionType.CASE_STUDY.value,
                            DEFAULT_MARKS[QuestionType.CASE_STUDY.value], context.text),
    )


def _gen_essay(units: list[MaterialUnit], topic_name: str, rng: random.Random) -> QuestionDraft | None:
    candidates = [u for u in units if len(u.text) >= 80]
    if not candidates:
        return None
    unit = rng.choice(candidates)
    prompt = (f"Critically evaluate {topic_name}. Construct a reasoned argument supported by "
              f"evidence from the coursework. Your answer should show analysis and evaluation.")
    return QuestionDraft(
        qtype=QuestionType.ESSAY.value,
        prompt=prompt,
        marks=DEFAULT_MARKS[QuestionType.ESSAY.value],
        difficulty=Difficulty.EXPERT.value,
        bloom=BloomLevel.EVALUATE.value,
        topic_id=unit.topic_id, subtopic_id=unit.subtopic_id, outcome_id=unit.outcome_id,
        payload={"answer_control": "textarea", "source_hint": unit.text[:400]},
        expected_answer=unit.text,
        explanation="Assessment focuses on argument, evidence, structure and critical evaluation.",
        provenance=unit.provenance,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        rubrics=[
            {"criterion": "Introduction and position stated", "marks": 4,
             "guidance": "Clear thesis or position.", "partial_credit": True},
            {"criterion": "Evidence and analysis", "marks": 8,
             "guidance": "Uses coursework evidence accurately.", "partial_credit": True},
            {"criterion": "Evaluation and judgement", "marks": 6,
             "guidance": "Weighs arguments and reaches a justified conclusion.", "partial_credit": True},
            {"criterion": "Structure and academic register", "marks": 2,
             "guidance": "Coherent structure and correct terminology.", "partial_credit": True},
        ],
    )


def _gen_diagram_question(asset: VisualAsset, units: list[MaterialUnit],
                          rng: random.Random) -> QuestionDraft | None:
    labels = [str(label) for label in (asset.labels or []) if str(label).strip()]
    related = [u for u in units if u.topic_id == asset.topic_id] or units
    if not related:
        return None
    unit = rng.choice(related)
    if labels:
        items = [{"prompt": f"Label {i + 1}", "answer": label}
                 for i, label in enumerate(labels[:5])]
        return QuestionDraft(
            qtype=QuestionType.DIAGRAM_LABELLING.value,
            prompt=(f"Study the {asset.diagram_type.replace('_', ' ')} below and supply the "
                    f"correct label for each numbered position."),
            marks=DEFAULT_MARKS[QuestionType.DIAGRAM_LABELLING.value],
            difficulty=Difficulty.INTERMEDIATE.value,
            bloom=BloomLevel.UNDERSTAND.value,
            topic_id=asset.topic_id, outcome_id=asset.learning_outcome_id,
            payload={"answer_control": "label_inputs", "items": items},
            expected_answer="; ".join(f"{i['prompt']}: {i['answer']}" for i in items),
            explanation="Labels correspond to the approved diagram version.",
            provenance=Provenance.GENERATED.value,
            source_document_ids=[unit.document_id] if unit.document_id else [],
            source_content_ids=[unit.content_id] if unit.content_id else [],
            visual_asset_id=asset.id, visual_version=asset.version,
            rubrics=_rubric_for(QuestionType.DIAGRAM_LABELLING.value,
                                DEFAULT_MARKS[QuestionType.DIAGRAM_LABELLING.value], "diagram labels"),
        )
    return QuestionDraft(
        qtype=QuestionType.DIAGRAM_INTERPRETATION.value,
        prompt=("Study the diagram below and explain what it represents, referring to the "
                "components and their relationships."),
        marks=DEFAULT_MARKS[QuestionType.DIAGRAM_INTERPRETATION.value],
        difficulty=Difficulty.ADVANCED.value,
        bloom=BloomLevel.ANALYSE.value,
        topic_id=asset.topic_id, outcome_id=asset.learning_outcome_id,
        payload={"answer_control": "textarea"},
        expected_answer=unit.text,
        explanation="A strong answer identifies each component and the relationship between them.",
        provenance=Provenance.GENERATED.value,
        source_document_ids=[unit.document_id] if unit.document_id else [],
        source_content_ids=[unit.content_id] if unit.content_id else [],
        visual_asset_id=asset.id, visual_version=asset.version,
        rubrics=_rubric_for(QuestionType.DIAGRAM_INTERPRETATION.value,
                            DEFAULT_MARKS[QuestionType.DIAGRAM_INTERPRETATION.value], unit.text),
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _expand_distribution(mix: dict[str, float], total: int,
                         available: list[str]) -> list[str]:
    """Largest-remainder allocation of `total` slots across `mix` keys."""
    mix = {k: v for k, v in mix.items() if k in available and v > 0}
    if not mix:
        mix = {k: 1.0 for k in available}
    weight_sum = sum(mix.values())
    raw = {k: (v / weight_sum) * total for k, v in mix.items()}
    counts = {k: int(raw[k]) for k in raw}
    remainder = total - sum(counts.values())
    for key, _ in sorted(raw.items(), key=lambda kv: -(raw[kv[0]] - int(raw[kv[0]]))):
        if remainder <= 0:
            break
        counts[key] += 1
        remainder -= 1
    slots: list[str] = []
    for key, count in counts.items():
        slots.extend([key] * count)
    return slots


def generate_questions(
    workspace_id: str,
    blueprint_id: str,
    version: int,
    question_count: int,
    total_marks: int,
    topic_bundles: list[dict],
    assets: list[VisualAsset],
    type_distribution: dict[str, float] | None = None,
    difficulty_distribution: dict[str, float] | None = None,
    bloom_distribution: dict[str, float] | None = None,
    required_visual_keys: list[str] | None = None,
    existing_fingerprints: set[str] | None = None,
) -> list[QuestionDraft]:
    """Generate a deterministic set of questions for a blueprint.

    ``topic_bundles`` is a list of dicts with keys ``topic`` (Topic),
    ``contents`` (list[ExtractedContent]), ``subtopics`` and ``outcomes``.
    """
    seed = int(hashlib.sha256(f"{workspace_id}:{blueprint_id}:{version}".encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    existing_fingerprints = existing_fingerprints or set()

    bundles = [b for b in topic_bundles if b["contents"]]
    if not bundles:
        return []

    material_by_topic: dict[str, list[MaterialUnit]] = {}
    definitions_by_topic: dict[str, list[tuple[str, str, MaterialUnit]]] = {}
    all_units: list[MaterialUnit] = []
    all_definitions: list[tuple[str, str, MaterialUnit]] = []
    for bundle in bundles:
        units = build_material(bundle["topic"], bundle["contents"],
                               bundle.get("subtopics", []), bundle.get("outcomes", []))
        material_by_topic[bundle["topic"].id] = units
        defs = _definitions(units)
        definitions_by_topic[bundle["topic"].id] = defs
        all_units.extend(units)
        all_definitions.extend(defs)

    if not all_units:
        return []

    # Available question types depend on the material actually present.
    available_types = [
        QuestionType.SINGLE_CHOICE.value, QuestionType.FILL_BLANK.value,
        QuestionType.SHORT_ANSWER.value, QuestionType.EXTENDED_RESPONSE.value,
        QuestionType.MATCHING.value, QuestionType.ORDERING.value,
        QuestionType.CASE_STUDY.value, QuestionType.ESSAY.value,
        QuestionType.MULTIPLE_CHOICE.value, QuestionType.NUMERICAL.value,
        QuestionType.FORMULA.value,
    ]
    if any(u.numbers for u in all_units):
        available_types.append(QuestionType.NUMERICAL.value)
    if any(u.kind == "formula" for u in all_units):
        available_types.append(QuestionType.FORMULA.value)
    available_types = sorted(set(available_types))

    approved_assets = [a for a in assets if a.status == "approved"]
    if required_visual_keys:
        approved_assets = [a for a in approved_assets if a.key in set(required_visual_keys)] or approved_assets
    if approved_assets:
        available_types.append(QuestionType.DIAGRAM_LABELLING.value)
        available_types.append(QuestionType.DIAGRAM_INTERPRETATION.value)

    type_mix = type_distribution or DEFAULT_TYPE_MIX
    difficulty_mix = difficulty_distribution or DEFAULT_DIFFICULTY_MIX
    bloom_mix = bloom_distribution or DEFAULT_BLOOM_MIX

    # Reserve one slot per approved required visual so visuals are assessed.
    visual_slots = min(len(approved_assets), max(1, question_count // 5)) if approved_assets else 0
    type_slots = _expand_distribution(type_mix, question_count - visual_slots, available_types)
    difficulty_slots = _expand_distribution(
        difficulty_mix, question_count, list(DIFFICULTY_WEIGHT.keys()))
    bloom_slots = _expand_distribution(bloom_mix, question_count, textutil.BLOOM_ORDER)
    rng.shuffle(type_slots)

    drafts: list[QuestionDraft] = []
    used_fingerprints: set[str] = set(existing_fingerprints)
    used_prompts: set[str] = set()
    topic_ids = [b["topic"].id for b in bundles]

    def _prompt_key(draft: QuestionDraft) -> str:
        return re.sub(r"\s+", " ", draft.prompt.strip().lower())

    def _pick_topic() -> str:
        # Round-robin-ish weighted choice keeps coverage broad.
        return rng.choice(topic_ids)

    def _try_add(draft: QuestionDraft | None) -> bool:
        if draft is None:
            return False
        fp = draft.fingerprint()
        prompt_key = _prompt_key(draft)
        if fp in used_fingerprints or prompt_key in used_prompts:
            return False
        used_fingerprints.add(fp)
        used_prompts.add(prompt_key)
        drafts.append(draft)
        return True

    def _generate_for_type(qtype: str, topic_id: str, target_difficulty: str,
                           target_bloom: str) -> QuestionDraft | None:
        units = material_by_topic.get(topic_id, [])
        defs = definitions_by_topic.get(topic_id, [])
        topic_name = next((b["topic"].name for b in bundles if b["topic"].id == topic_id), "this topic")
        generator = {
            QuestionType.FILL_BLANK.value: lambda: _gen_fill_blank(units, rng),
            QuestionType.SINGLE_CHOICE.value: lambda: _gen_single_choice(units, defs or all_definitions, rng),
            QuestionType.MULTIPLE_CHOICE.value: lambda: _gen_multiple_choice(units, defs or all_definitions, rng),
            QuestionType.MATCHING.value: lambda: _gen_matching(
                units, defs or all_definitions, rng, topic_name),
            QuestionType.ORDERING.value: lambda: _gen_ordering(units, rng, topic_name),
            QuestionType.NUMERICAL.value: lambda: _gen_numerical(units, rng),
            QuestionType.FORMULA.value: lambda: _gen_formula(units, rng),
            QuestionType.SHORT_ANSWER.value: lambda: _gen_short_answer(units, defs, rng),
            QuestionType.EXTENDED_RESPONSE.value: lambda: _gen_extended(units, topic_name, rng),
            QuestionType.CASE_STUDY.value: lambda: _gen_case_study(units, topic_name, rng),
            QuestionType.ESSAY.value: lambda: _gen_essay(units, topic_name, rng),
        }.get(qtype)
        if generator is None:
            return None
        for _ in range(6):
            draft = generator()
            if draft is None:
                return None
            if target_difficulty:
                draft.difficulty = target_difficulty
            if target_bloom:
                draft.bloom = target_bloom
            if draft.fingerprint() not in used_fingerprints:
                return draft
        return None

    for i, qtype in enumerate(type_slots):
        difficulty = difficulty_slots[i % len(difficulty_slots)]
        bloom = bloom_slots[i % len(bloom_slots)]
        added = False
        for _ in range(len(topic_ids) + 2):
            topic_id = _pick_topic()
            if _try_add(_generate_for_type(qtype, topic_id, difficulty, bloom)):
                added = True
                break
        if not added:
            # Fall back to another type that can be produced from the material.
            for alt in available_types:
                if alt == qtype:
                    continue
                if _try_add(_generate_for_type(alt, _pick_topic(), difficulty, bloom)):
                    added = True
                    break

    for asset in approved_assets[:visual_slots]:
        units = material_by_topic.get(asset.topic_id or "", all_units) or all_units
        _try_add(_gen_diagram_question(asset, units, rng))

    _normalise_marks(drafts, total_marks)
    for draft in drafts:
        _rescale_rubrics(draft)
        draft.validation_notes = _validate(draft)
    _assign_sections(drafts)
    return drafts


def _rescale_rubrics(draft: QuestionDraft) -> None:
    """Keep rubric marks summing exactly to the question's final mark value.

    Marks are rebalanced after generation to hit the blueprint total, so rubrics
    created with the generator's default marks must be rescaled or a correct
    answer could never earn full credit.
    """
    if not draft.rubrics:
        return
    total = sum(int(r.get("marks", 1)) for r in draft.rubrics)
    if total == draft.marks:
        return
    if total <= 0:
        share = draft.marks / len(draft.rubrics)
        for rubric in draft.rubrics:
            rubric["marks"] = max(1, round(share))
        return

    exact = [int(r.get("marks", 1)) * draft.marks / total for r in draft.rubrics]
    floors = [max(1, int(value)) for value in exact]
    remainder = draft.marks - sum(floors)
    order = sorted(range(len(exact)), key=lambda i: -(exact[i] - int(exact[i])))
    index = 0
    while remainder > 0:
        floors[order[index % len(order)]] += 1
        remainder -= 1
        index += 1
    # If rounding overshot, trim the largest criteria first (never below one).
    index = 0
    while sum(floors) > draft.marks:
        target = order[len(order) - 1 - (index % len(order))]
        if floors[target] > 1:
            floors[target] -= 1
        index += 1
        if index > len(order) * 200:
            break
    for rubric, marks in zip(draft.rubrics, floors):
        rubric["marks"] = marks


def _normalise_marks(drafts: list[QuestionDraft], total_marks: int) -> None:
    if not drafts or total_marks <= 0:
        return
    current = sum(d.marks for d in drafts)
    if current == total_marks:
        return
    if current < total_marks:
        # Distribute the shortfall to the highest-value questions first.
        order = sorted(range(len(drafts)), key=lambda i: -drafts[i].marks)
        remaining = total_marks - current
        i = 0
        while remaining > 0 and order:
            drafts[order[i % len(order)]].marks += 1
            remaining -= 1
            i += 1
    else:
        # Trim proportionally but never below one mark.
        order = sorted(range(len(drafts)), key=lambda i: -drafts[i].marks)
        excess = current - total_marks
        i = 0
        while excess > 0 and order:
            idx = order[i % len(order)]
            if drafts[idx].marks > 1:
                drafts[idx].marks -= 1
                excess -= 1
            i += 1
            if i > len(order) * 200:
                break


def _assign_sections(drafts: list[QuestionDraft]) -> None:
    """Group by cognitive demand into A/B/C sections, as real papers do."""
    for draft in drafts:
        if draft.qtype in {QuestionType.SINGLE_CHOICE.value, QuestionType.MULTIPLE_CHOICE.value,
                           QuestionType.FILL_BLANK.value, QuestionType.MATCHING.value}:
            draft.payload["section"] = "Section A — Objective"
        elif draft.qtype in {QuestionType.NUMERICAL.value, QuestionType.FORMULA.value,
                             QuestionType.ORDERING.value, QuestionType.SHORT_ANSWER.value,
                             QuestionType.DIAGRAM_LABELLING.value,
                             QuestionType.DIAGRAM_INTERPRETATION.value}:
            draft.payload["section"] = "Section B — Structured"
        else:
            draft.payload["section"] = "Section C — Extended Response"


def _validate(draft: QuestionDraft) -> str:
    issues: list[str] = []
    if not draft.prompt.strip():
        issues.append("empty prompt")
    if draft.marks < 1:
        issues.append("non-positive marks")
    if draft.qtype in {QuestionType.SINGLE_CHOICE.value, QuestionType.MULTIPLE_CHOICE.value}:
        if len(draft.options) < 2:
            issues.append("insufficient options")
        if draft.qtype == QuestionType.MULTIPLE_CHOICE.value and len(draft.payload.get("correct", [])) < 2:
            issues.append("multiple-choice requires at least two correct options")
    if draft.qtype == QuestionType.FILL_BLANK.value:
        if draft.payload.get("answer_control") != "text_box":
            issues.append("fill-in questions must use a text box")
        if "________" not in draft.prompt:
            issues.append("no blank present in prompt")
    if draft.qtype == QuestionType.MATCHING.value and not draft.payload.get("items"):
        issues.append("matching question has no items")
    if draft.qtype == QuestionType.ORDERING.value and len(draft.payload.get("correct_order", [])) < 2:
        issues.append("ordering question has no correct sequence")
    if not draft.expected_answer.strip():
        issues.append("missing expected answer")
    if draft.qtype in {QuestionType.EXTENDED_RESPONSE.value, QuestionType.ESSAY.value,
                       QuestionType.CASE_STUDY.value, QuestionType.SHORT_ANSWER.value}:
        if not draft.rubrics:
            issues.append("missing marking rubric")
    return "; ".join(issues)


def section_marks(drafts: list[QuestionDraft]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for draft in drafts:
        section = draft.payload.get("section", "Section A — Objective")
        totals[section] = totals.get(section, 0) + draft.marks
    return totals
