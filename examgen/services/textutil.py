"""Shared academic text utilities: tokenisation, sentence splitting, Bloom mapping."""

from __future__ import annotations

import re

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "as", "of",
    "to", "in", "on", "at", "by", "for", "with", "from", "into", "onto", "over",
    "under", "about", "above", "below", "between", "is", "are", "was", "were",
    "be", "been", "being", "am", "do", "does", "did", "done", "have", "has",
    "had", "having", "will", "would", "shall", "should", "can", "could", "may",
    "might", "must", "this", "that", "these", "those", "it", "its", "they",
    "them", "their", "there", "here", "where", "when", "which", "who", "whom",
    "whose", "what", "why", "how", "not", "no", "nor", "you", "your", "we",
    "our", "i", "he", "she", "his", "her", "him", "also", "such", "more",
    "most", "other", "some", "any", "all", "each", "both", "few", "many",
    "much", "own", "same", "too", "very", "just", "only", "one", "two",
    "e", "g", "etc", "ie", "eg", "figure", "table", "page", "chapter",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-']+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])|\n+")

# Command verbs -> Bloom level. Ordered by specificity.
_BLOOM_VERBS: list[tuple[str, tuple[str, ...]]] = [
    ("create", ("design", "construct", "develop", "formulate", "compose", "devise",
                "produce", "build", "create", "generate")),
    ("evaluate", ("evaluate", "justify", "critique", "assess", "appraise",
                  "recommend", "argue", "defend", "validate")),
    ("analyse", ("analyse", "analyze", "compare", "contrast", "differentiate",
                 "distinguish", "examine", "investigate", "diagnose", "categorise",
                 "categorize", "classify")),
    ("apply", ("apply", "calculate", "compute", "solve", "demonstrate", "implement",
               "use", "perform", "derive", "determine", "convert", "interpret")),
    ("understand", ("explain", "describe", "summarise", "summarize", "discuss",
                    "illustrate", "identify", "outline", "interpret", "clarify",
                    "paraphrase")),
    ("remember", ("define", "list", "state", "name", "recall", "recite",
                  "recognise", "recognize", "label", "match", "select")),
]

BLOOM_ORDER = ["remember", "understand", "apply", "analyse", "evaluate", "create"]

DIAGRAM_KEYWORDS = {
    "uml": ("uml", "class diagram", "sequence diagram", "use case", "activity diagram",
            "state diagram", "interaction diagram"),
    "er_diagram": ("entity relationship", "er diagram", "erd", "cardinality",
                   "normalisation", "normalization", "foreign key"),
    "network_topology": ("network topology", "topology", "subnet", "router", "switch",
                         "firewall", "vlan", "lan", "wan", "osi", "tcp/ip"),
    "architecture": ("system architecture", "architecture", "component diagram",
                     "deployment diagram", "layer", "microservice", "three-tier"),
    "flowchart": ("flowchart", "flow chart", "algorithm", "pseudocode", "decision tree",
                  "process flow", "workflow"),
    "circuit": ("circuit", "resistor", "capacitor", "voltage", "current", "ohms",
                "kirchhoff", "transistor", "logic gate", "op-amp"),
    "graph": ("graph", "plot", "curve", "axis", "coordinates", "slope", "parabola",
              "histogram", "scatter", "function f(", "gradient"),
    "scientific": ("cell", "molecule", "organ", "anatomy", "reaction", "biology",
                   "physics", "apparatus", "specimen", "structure of"),
    "project_network": ("critical path", "pert", "gantt", "precedence", "network diagram",
                        "earliest start", "float"),
    "table": ("table", "spreadsheet", "dataset", "record", "field", "column", "row"),
}

NUMERIC_HINTS = re.compile(
    r"(\b\d+(?:\.\d+)?\b\s*[%°]|\b[a-zA-Z]\s*=\s*|∑|∫|\bcalculate\b|\bcompute\b|"
    r"\bsolve\b|\bevaluate\b\s+the\s+expression|\bhow\s+many\b|\bhow\s+much\b)",
    re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 2]


def sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_RE.split(text) if s and s.strip()]
    return [p for p in parts if len(p) > 15]


def bloom_for(sentence: str) -> str:
    lowered = sentence.lower()
    for level, verbs in _BLOOM_VERBS:
        for verb in verbs:
            if re.search(rf"\b{re.escape(verb)}\w*\b", lowered):
                return level
    return "understand"


def keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    """Count keyword occurrences with word boundaries for single words.

    Plain substring counting would let ``organ`` match ``organisation`` and
    ``cell`` match ``excellent``, which produces spurious visual requirements.
    Multi-word phrases are matched as substrings.
    """
    total = 0
    for keyword in keywords:
        if " " in keyword:
            total += text.count(keyword)
        else:
            total += len(re.findall(rf"\b{re.escape(keyword)}\b", text))
    return total


def detect_diagram_type(text: str) -> str | None:
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for diagram_type, keywords in DIAGRAM_KEYWORDS.items():
        score = keyword_hits(lowered, keywords)
        if score and (best is None or score > best[0]):
            best = (score, diagram_type)
    return best[1] if best else None


def has_numeric_content(text: str) -> bool:
    return bool(NUMERIC_HINTS.search(text))


def title_case_topic(text: str) -> str:
    text = text.strip().strip("#*:.-").strip()
    if not text:
        return text
    if text.isupper():
        text = text.title()
    return text[:120]
