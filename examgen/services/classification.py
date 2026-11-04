"""Subject and topic intelligence.

Builds the academic hierarchy

    Subject/Module -> Topic -> Subtopic -> Learning Outcome -> Question

strictly from the content extracted from the *selected* workspace's documents.
Nothing is inferred across workspaces. Where the coursework is thin the service
reports the gap instead of inventing material.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..models import (
    AcademicDocument,
    CoverageLevel,
    DocumentStatus,
    ExtractedContent,
    ProcessingStatus,
    Provenance,
    VisualRequirement,
)
from . import textutil

MIN_TOPIC_CHARS = 120
OUTCOMES_PER_TOPIC = 5
_MAX_TOPICS = 24

_DEFINITION_RE = re.compile(
    r"\b(?P<term>[A-Za-z][A-Za-z0-9 \-]{2,60}?)\s+"
    r"(?:is|are|refers to|means|is defined as|can be defined as|denotes)\b",
    re.IGNORECASE,
)
_PROCEDURE_RE = re.compile(
    r"\b(?:step\s+\d+|first|then|next|finally|procedure|algorithm|process|"
    r"methodology|sequence)\b", re.IGNORECASE)


@dataclass
class OutcomeDraft:
    statement: str
    bloom: str
    evidence: str = ""


@dataclass
class SubtopicDraft:
    name: str
    summary: str = ""
    coverage: str = CoverageLevel.ADEQUATE.value
    outcomes: list[OutcomeDraft] = field(default_factory=list)


@dataclass
class TopicDraft:
    name: str
    summary: str = ""
    coverage: str = CoverageLevel.ADEQUATE.value
    coverage_notes: str = ""
    needs_visual: str = VisualRequirement.UNNECESSARY.value
    visual_rationale: str = ""
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.0
    content_ids: list[str] = field(default_factory=list)
    subtopics: list[SubtopicDraft] = field(default_factory=list)


@dataclass
class ClassificationResult:
    topics: list[TopicDraft]
    conflicts: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)


def _tf(chunks: list[ExtractedContent]) -> Counter:
    counts: Counter = Counter()
    for chunk in chunks:
        counts.update(textutil.content_tokens(chunk.text))
    return counts


def _seed_from_headings(chunks: list[ExtractedContent]) -> list[str]:
    seeds: list[str] = []
    for chunk in chunks:
        if chunk.kind == "heading" and chunk.text.strip():
            label = textutil.title_case_topic(chunk.text)
            if 2 <= len(label) <= 120 and label.lower() not in {s.lower() for s in seeds}:
                seeds.append(label)
    return seeds


def _seed_from_frequency(chunks: list[ExtractedContent], limit: int = 12) -> list[str]:
    """Fallback topic discovery when a document has no usable headings.

    Frequent, meaningful noun-phrase-like n-grams are promoted to topics. This
    is a heuristic over the student's own material — not external knowledge.

    A bigram is dropped when a trigram that contains it occurs at least as
    often, so "first search" collapses into "breadth first search" instead of
    being offered as a topic in its own right.
    """
    bigrams: Counter = Counter()
    trigrams: Counter = Counter()
    unigrams: Counter = Counter()
    for chunk in chunks:
        tokens = textutil.content_tokens(chunk.text)
        unigrams.update(tokens)
        for a, b in zip(tokens, tokens[1:]):
            if a != b:
                bigrams[f"{a} {b}"] += 1
        for a, b, c in zip(tokens, tokens[1:], tokens[2:]):
            if a != b and b != c:
                trigrams[f"{a} {b} {c}"] += 1

    def _subsumed(bigram: str) -> bool:
        contained = sum(count for trigram, count in trigrams.items() if bigram in trigram)
        return contained >= bigrams[bigram]

    phrases = [phrase for phrase, count in trigrams.most_common(40) if count >= 2]
    phrases += [phrase for phrase, count in bigrams.most_common(60)
                if count >= 3 and not _subsumed(phrase)]
    ranked = list(phrases)
    phrase_words = {word for phrase in phrases for word in phrase.split()}
    # A unigram that already forms part of a kept phrase is a fragment, e.g.
    # "sort" inside "bubble sort", so it is not offered as its own topic.
    ranked += [word for word, count in unigrams.most_common(30)
               if count >= 4 and word not in phrase_words]
    seeds: list[str] = []
    for phrase in ranked:
        label = textutil.title_case_topic(phrase)
        if all(label.lower() not in s.lower() and s.lower() not in label.lower() for s in seeds):
            seeds.append(label)
        if len(seeds) >= limit:
            break
    return seeds


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / norm if norm else 0.0


def _assign(chunks: list[ExtractedContent], seeds: list[str]) -> dict[str, list[ExtractedContent]]:
    """Assign each chunk to its best-matching topic seed by token similarity."""
    seed_vectors = {s: Counter(textutil.content_tokens(s)) for s in seeds}
    groups: dict[str, list[ExtractedContent]] = defaultdict(list)
    unassigned: list[ExtractedContent] = []
    for chunk in chunks:
        vector = Counter(textutil.content_tokens(chunk.text))
        if not vector:
            unassigned.append(chunk)
            continue
        best_seed, best_score = None, 0.0
        for seed, seed_vec in seed_vectors.items():
            score = _cosine(vector, seed_vec)
            if score > best_score:
                best_seed, best_score = seed, score
        if best_seed and best_score >= 0.06:
            groups[best_seed].append(chunk)
        else:
            unassigned.append(chunk)
    if unassigned:
        groups.setdefault("General Concepts", []).extend(unassigned)
    return groups


def _outcomes_for(chunks: list[ExtractedContent]) -> list[OutcomeDraft]:
    outcomes: list[OutcomeDraft] = []
    seen: set[str] = set()
    for chunk in chunks:
        for sentence in textutil.sentences(chunk.text):
            if len(sentence) > 300:
                sentence = sentence[:300].rsplit(" ", 1)[0] + "…"
            key = sentence.lower()[:80]
            if key in seen:
                continue
            bloom = textutil.bloom_for(sentence)
            is_definition = bool(_DEFINITION_RE.search(sentence))
            is_procedure = bool(_PROCEDURE_RE.search(sentence))
            if not (is_definition or is_procedure or bloom in {"apply", "analyse", "evaluate", "create"}):
                continue
            seen.add(key)
            outcomes.append(OutcomeDraft(statement=sentence.strip(), bloom=bloom,
                                         evidence=chunk.id))
            if len(outcomes) >= OUTCOMES_PER_TOPIC:
                return outcomes
    return outcomes


def _subtopics_for(name: str, chunks: list[ExtractedContent]) -> list[SubtopicDraft]:
    headings = [c for c in chunks if c.kind == "heading" and c.text.strip()]
    drafts: list[SubtopicDraft] = []
    if len(headings) >= 2:
        for heading in headings[:8]:
            label = textutil.title_case_topic(heading.text)
            if label.lower() == name.lower():
                continue
            related = [c for c in chunks if c.heading and c.heading.strip() == heading.text.strip()]
            drafts.append(SubtopicDraft(
                name=label,
                summary=(related[0].text[:240] if related else ""),
                coverage=(CoverageLevel.ADEQUATE.value if len(related) >= 3
                          else CoverageLevel.PARTIAL.value),
                outcomes=_outcomes_for(related[:6]),
            ))
    if not drafts:
        # Derive subtopics from the strongest recurring keyword phrases.
        counter: Counter = Counter()
        for chunk in chunks:
            tokens = textutil.content_tokens(chunk.text)
            for a, b in zip(tokens, tokens[1:]):
                counter[f"{a} {b}"] += 1
        for phrase, count in counter.most_common(4):
            if count < 2:
                continue
            related = [c for c in chunks if phrase in c.text.lower()]
            drafts.append(SubtopicDraft(
                name=textutil.title_case_topic(phrase),
                summary=(related[0].text[:240] if related else ""),
                coverage=(CoverageLevel.ADEQUATE.value if len(related) >= 3
                          else CoverageLevel.PARTIAL.value),
                outcomes=_outcomes_for(related[:6]),
            ))
    if not drafts:
        drafts.append(SubtopicDraft(
            name=f"{name} — Core Concepts",
            summary=(chunks[0].text[:240] if chunks else ""),
            coverage=CoverageLevel.PARTIAL.value,
            outcomes=_outcomes_for(chunks[:6]),
        ))
    return drafts[:8]


def _visual_requirement(text: str) -> tuple[str, str, str | None]:
    diagram = textutil.detect_diagram_type(text)
    if not diagram:
        return VisualRequirement.UNNECESSARY.value, "", None
    lowered = text.lower()
    hits = textutil.keyword_hits(lowered, textutil.DIAGRAM_KEYWORDS[diagram])
    if hits >= 3 or textutil.has_numeric_content(text) and diagram in {"graph", "circuit"}:
        return (VisualRequirement.ESSENTIAL.value,
                f"Frequent {diagram.replace('_', ' ')} references and diagram-dependent content.",
                diagram)
    return (VisualRequirement.BENEFICIAL.value,
            f"{diagram.replace('_', ' ').title()} references suggest a supporting diagram.",
            diagram)


def _detect_duplicates(chunks: list[ExtractedContent]) -> list[dict]:
    duplicates: list[dict] = []
    seen: dict[str, ExtractedContent] = {}
    for chunk in chunks:
        norm = re.sub(r"\W+", " ", chunk.text.lower()).strip()
        if len(norm) < 60:
            continue
        signature = norm[:180]
        if signature in seen:
            duplicates.append({
                "content_id": chunk.id,
                "duplicate_of": seen[signature].id,
                "document_id": chunk.document_id,
                "excerpt": chunk.text[:160],
            })
        else:
            seen[signature] = chunk
    return duplicates


_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def _detect_conflicts(chunks: list[ExtractedContent]) -> list[dict]:
    """Flag the same statement carrying different numbers across documents."""
    conflicts: list[dict] = []
    by_skeleton: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for chunk in chunks:
        for sentence in textutil.sentences(chunk.text):
            skeleton = _NUMBER_RE.sub("#", sentence.lower())
            skeleton = re.sub(r"\W+", " ", skeleton).strip()
            if len(skeleton) < 40:
                continue
            numbers = tuple(_NUMBER_RE.findall(sentence))
            if numbers:
                by_skeleton[skeleton[:160]].append((sentence, chunk.document_id, chunk.id))
    for skeleton, entries in by_skeleton.items():
        distinct = {tuple(_NUMBER_RE.findall(e[0])) for e in entries}
        docs = {e[1] for e in entries}
        if len(distinct) > 1 and len(docs) > 1:
            conflicts.append({
                "skeleton": skeleton,
                "variants": [{"text": e[0][:200], "document_id": e[1]} for e in entries[:4]],
                "message": "Conflicting numeric values for the same statement across documents.",
            })
    return conflicts[:20]


def classify(workspace_id: str, documents: list[AcademicDocument],
             chunks: list[ExtractedContent]) -> ClassificationResult:
    """Classify extracted content into topics, subtopics and learning outcomes."""
    usable = [c for c in chunks if len(c.text.strip()) >= 25]
    if not usable:
        return ClassificationResult(topics=[])

    seeds = _seed_from_headings(usable)
    if len(seeds) < 3:
        seeds = _seed_from_headings(usable) + _seed_from_frequency(usable)
    seeds = [s for s in seeds if s.strip()][:_MAX_TOPICS]
    if not seeds:
        seeds = ["General Concepts"]

    groups = _assign(usable, seeds)
    document_ids = {d.id for d in documents}
    previous_assessment_docs = {d.id for d in documents if d.kind == "previous_assessment"}

    topics: list[TopicDraft] = []
    for name, chunks_in_topic in groups.items():
        char_total = sum(len(c.text) for c in chunks_in_topic)
        if char_total < MIN_TOPIC_CHARS and len(groups) > 1:
            coverage = CoverageLevel.PARTIAL.value
            notes = "Limited content detected for this topic."
        else:
            coverage = CoverageLevel.ADEQUATE.value
            notes = ""
        combined = "\n".join(c.text for c in chunks_in_topic[:40])
        visual_requirement, rationale, _diagram = _visual_requirement(combined)
        keywords = [w for w, _ in Counter(
            textutil.content_tokens(combined)).most_common(12)]
        subtopics = _subtopics_for(name, chunks_in_topic)
        outcome_count = sum(len(s.outcomes) for s in subtopics)
        confidence = min(1.0, round(
            (min(char_total, 4000) / 4000) * 0.5
            + min(outcome_count, 6) / 6 * 0.3
            + (0.2 if name in _seed_from_headings(usable) else 0.0), 3))
        if coverage == CoverageLevel.ADEQUATE.value and outcome_count == 0:
            coverage = CoverageLevel.PARTIAL.value
            notes = "Content present but no explicit learning outcomes were stated."
        topics.append(TopicDraft(
            name=name,
            summary=combined[:400],
            coverage=coverage,
            coverage_notes=notes,
            needs_visual=visual_requirement,
            visual_rationale=rationale,
            keywords=keywords,
            confidence=confidence,
            content_ids=[c.id for c in chunks_in_topic],
            subtopics=subtopics,
        ))

    topics.sort(key=lambda t: (-t.confidence, t.name))
    result = ClassificationResult(
        topics=topics,
        duplicates=_detect_duplicates(usable),
        conflicts=_detect_conflicts(usable),
    )
    return result


def assess_sufficiency(workspace_id: str, documents: list[AcademicDocument],
                       chunks: list[ExtractedContent],
                       classification: ClassificationResult) -> dict:
    """Evaluate whether the uploaded material supports examination generation."""
    adequate = [t.name for t in classification.topics
                if t.coverage == CoverageLevel.ADEQUATE.value]
    partial = [t.name for t in classification.topics
               if t.coverage == CoverageLevel.PARTIAL.value]
    missing_outcomes = [
        f"{t.name}: no explicit learning outcomes stated" for t in classification.topics
        if not any(s.outcomes for s in t.subtopics)]

    total_chars = sum(len(c.text) for c in chunks)
    # Topics referenced in previous assessment papers but absent from coursework.
    previous_docs = {d.id for d in documents if d.kind == "previous_assessment"}
    coursework_text = " ".join(c.text.lower() for c in chunks if c.document_id not in previous_docs)
    missing: list[str] = []
    for chunk in chunks:
        if chunk.document_id not in previous_docs:
            continue
        for sentence in textutil.sentences(chunk.text):
            terms = [w for w in textutil.content_tokens(sentence) if len(w) > 4]
            if len(terms) < 3:
                continue
            overlap = sum(1 for w in set(terms) if w in coursework_text)
            if overlap / max(len(set(terms)), 1) < 0.25:
                snippet = sentence.strip()[:120]
                if snippet not in missing:
                    missing.append(snippet)
    missing = missing[:10]

    insufficient_types: list[str] = []
    if not any(textutil.has_numeric_content(c.text) for c in chunks):
        insufficient_types.append("numerical_calculation")
    if total_chars < 3000:
        insufficient_types.append("extended_response")
    if len([t for t in classification.topics
            if t.needs_visual != VisualRequirement.UNNECESSARY.value]) == 0:
        insufficient_types.append("diagram_based")

    clarifications: list[str] = []
    failed = [d for d in documents if d.processing_status == ProcessingStatus.ERROR.value]
    if failed:
        clarifications.append(
            f"{len(failed)} document(s) could not be fully processed: "
            + ", ".join(d.filename for d in failed[:5]))
    if not documents:
        clarifications.append("No documents uploaded for this subject yet.")

    document_count = len(documents)
    if document_count == 0:
        verdict = "insufficient"
    elif not adequate:
        verdict = "insufficient"
    elif partial or missing or insufficient_types:
        verdict = "partial"
    else:
        verdict = "sufficient"

    return {
        "adequate": adequate,
        "partial": partial,
        "missing": missing,
        "missing_outcomes": missing_outcomes,
        "conflicts": classification.conflicts,
        "insufficient_types": insufficient_types,
        "clarifications": clarifications,
        "document_count": document_count,
        "total_chars": total_chars,
        "verdict": verdict,
        "duplicates": classification.duplicates,
    }


def classify_document_kind(filename: str, content_type: str) -> str:
    lowered = filename.lower()
    if any(k in lowered for k in ("memo", "memorandum", "marking guide", "answer key", "solutions")):
        return "memorandum"
    if any(k in lowered for k in ("exam", "test", "paper", "assessment", "quiz", "past paper")):
        return "previous_assessment"
    if any(k in lowered for k in ("study guide", "revision", "notes summary")):
        return "study_guide"
    if any(k in lowered for k in ("practical", "lab", "assignment", "activity")):
        return "coursework_activity"
    return "coursework"
