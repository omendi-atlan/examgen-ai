"""Visual intelligence: requirement analysis, diagram construction and validation.

The platform deliberately favours *structured diagram construction* over opaque
image generation. Every approved visual is a versioned specification that the
server renders to SVG deterministically, so labels, relationships and values stay
editable, reviewable and auditable.

Nothing here invents academic content. Auto-drafted specifications are derived
from material the workspace already holds (topic names and stated learning
outcomes) and are always recorded as ``auto_draft`` provenance requiring human
approval. Numeric charts require an explicit specification because the platform
will not fabricate data.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

VISUAL_ANALYSER_VERSION = "visual-requirement-analysis-v1"
VISUAL_RENDERER_VERSION = "structured-svg-renderer-v1"

# Deterministic keyword signals. Order matters: the first matching kind wins for a
# topic so results are reproducible across runs.
DIAGRAM_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("er_diagram", ("database", "normalisation", "normalization", "schema", "entity", "relational", "foreign key", "primary key")),
    ("uml_class", ("uml", "class diagram", "inheritance", "polymorphism", "object-oriented", "object oriented")),
    ("network", ("network", "topology", "routing", "protocol", "subnet", "bandwidth", "packet")),
    ("tree", ("tree", "hierarchy", "taxonomy", "heap", "decision", "trie", "bst")),
    ("cycle", ("cycle", "loop", "recursion", "recursive", "iteration", "lifecycle", "feedback")),
    ("flowchart", ("algorithm", "flow", "workflow", "procedure", "process", "pipeline", "steps", "sequence of")),
    ("line_chart", ("growth", "trend", "over time", "rate of change", "time series", "complexity curve")),
    ("bar_chart", ("comparison", "compare", "distribution", "frequency", "benchmark", "complexity", "throughput")),
    ("table", ("table", "matrix", "truth table", "comparison of", "difference between")),
)

# Kinds whose meaning is structural; they can be auto-drafted from stated outcomes.
STRUCTURAL_KINDS = frozenset({"flowchart", "process", "cycle", "tree", "network", "er_diagram", "uml_class", "table"})
# Kinds that carry data; the platform will not invent the numbers.
DATA_KINDS = frozenset({"bar_chart", "line_chart"})
SUPPORTED_KINDS = STRUCTURAL_KINDS | DATA_KINDS

MAX_NODES = 40
MAX_EDGES = 80
MAX_LABEL_CHARS = 240
_LABEL_WRAP_CHARS = 26

_FORBIDDEN_SVG = (
    "<script",
    "<foreignobject",
    "javascript:",
    "onload=",
    "onerror=",
    "onclick=",
    "onmouseover=",
    "<iframe",
    "<embed",
    "<use",
    "xlink:href",
    "href=",
)


class VisualSpecInvalid(ValueError):
    """The supplied or derived diagram specification is not usable."""


@dataclass
class RequirementDetermination:
    """One topic's visual requirement verdict with its supporting evidence."""

    topic_id: str
    topic_name: str
    level: str
    recommended_kind: str | None
    proposed_title: str
    rationale: str
    signals: dict[str, object] = field(default_factory=dict)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _matched_signals(topic_name: str) -> list[tuple[str, str]]:
    """Return (kind, keyword) pairs whose keyword appears in the topic name."""
    haystack = f" {_normalise(topic_name)} "
    matches: list[tuple[str, str]] = []
    for kind, keywords in DIAGRAM_SIGNALS:
        for keyword in keywords:
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", haystack):
                matches.append((kind, keyword))
    return matches


def determine_requirement(topic_id: str, topic_name: str, outcome_count: int = 0) -> RequirementDetermination:
    """Deterministically classify whether a topic needs a visual representation.

    Two or more independent keyword signals make a visual *essential*; one signal
    makes it *beneficial*; none leaves it *unnecessary*. The rule is intentionally
    simple, explainable and reproducible.
    """
    matches = _matched_signals(topic_name)
    kinds = [kind for kind, _ in matches]
    recommended_kind = kinds[0] if kinds else None
    # A single distinct signal is "beneficial"; corroborating signals escalate.
    distinct_kinds = len(dict.fromkeys(kinds))
    signal_count = len(matches)

    if signal_count >= 2 or distinct_kinds >= 2:
        level = "essential"
    elif signal_count == 1:
        level = "beneficial"
    else:
        level = "unnecessary"

    rationale_parts: list[str] = []
    if matches:
        described = ", ".join(f"'{keyword}' ({kind})" for kind, keyword in matches)
        rationale_parts.append(f"Topic wording signals {described}.")
    else:
        rationale_parts.append("No structural, relational or data-comparison terminology was detected.")
    if outcome_count and level != "unnecessary":
        rationale_parts.append(f"{outcome_count} stated learning outcome(s) support a diagram.")
    if level == "essential":
        rationale_parts.append("Multiple independent signals make a visual representation essential.")
    elif level == "beneficial":
        rationale_parts.append("A single signal suggests a visual would aid understanding.")

    return RequirementDetermination(
        topic_id=topic_id,
        topic_name=topic_name,
        level=level,
        recommended_kind=recommended_kind if level != "unnecessary" else None,
        proposed_title=f"{topic_name} — {_kind_title(recommended_kind)}" if recommended_kind else topic_name,
        rationale=" ".join(rationale_parts),
        signals={"matched_keywords": [kw for _, kw in matches], "matched_kinds": kinds, "signal_count": signal_count},
    )


def _kind_title(kind: str | None) -> str:
    return {
        "flowchart": "process flow",
        "process": "process flow",
        "cycle": "cycle diagram",
        "tree": "hierarchy diagram",
        "network": "network diagram",
        "er_diagram": "entity relationship diagram",
        "uml_class": "class diagram",
        "bar_chart": "comparison chart",
        "line_chart": "trend chart",
        "table": "structured comparison",
    }.get(kind or "", "diagram")


def build_auto_draft_spec(
    *,
    title: str,
    kind: str,
    outcome_labels: Sequence[str],
) -> dict[str, object]:
    """Draft a structural diagram from the workspace's own stated learning outcomes.

    This is explicitly a draft scaffold. It visualises outcomes the workspace
    already declares; it does not assert new academic facts.
    """
    if kind not in STRUCTURAL_KINDS:
        raise VisualSpecInvalid(
            f"'{kind}' carries data and cannot be auto-drafted; supply an explicit specification."
        )
    labels = [label.strip() for label in outcome_labels if label and label.strip()]
    if not labels:
        raise VisualSpecInvalid("Auto-drafting a visual requires at least one stated learning outcome.")
    labels = labels[:MAX_NODES]
    nodes = [
        {"id": f"n{index + 1}", "label": label[:MAX_LABEL_CHARS]}
        for index, label in enumerate(labels)
    ]
    if kind == "cycle" and len(nodes) >= 3:
        edges = [
            {"source": nodes[index]["id"], "target": nodes[(index + 1) % len(nodes)]["id"]}
            for index in range(len(nodes))
        ]
    elif kind in {"tree", "network", "er_diagram", "uml_class"} and len(nodes) >= 2:
        edges = [
            {"source": nodes[index]["id"], "target": nodes[index + 1]["id"]}
            for index in range(len(nodes) - 1)
        ]
    else:
        edges = [
            {"source": nodes[index]["id"], "target": nodes[index + 1]["id"]}
            for index in range(len(nodes) - 1)
        ]
    return {
        "title": title.strip()[:MAX_LABEL_CHARS] or "Untitled visual",
        "kind": kind,
        "nodes": nodes,
        "edges": edges,
        "provenance": {"source": "auto_draft"},
    }


def validate_spec(spec: dict[str, object]) -> dict[str, object]:
    """Structurally validate a diagram specification and return a report."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(spec, dict):
        raise VisualSpecInvalid("A diagram specification must be a JSON object.")
    kind = spec.get("kind")
    if kind not in SUPPORTED_KINDS:
        raise VisualSpecInvalid(f"Unsupported diagram kind: {kind!r}.")
    title = spec.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("A non-empty title is required.")
    elif len(title) > MAX_LABEL_CHARS:
        errors.append(f"Title must not exceed {MAX_LABEL_CHARS} characters.")

    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise VisualSpecInvalid("'nodes' and 'edges' must be lists.")
    if len(nodes) > MAX_NODES:
        errors.append(f"At most {MAX_NODES} nodes are supported.")
    if len(edges) > MAX_EDGES:
        errors.append(f"At most {MAX_EDGES} edges are supported.")
    if kind == "table":
        if not spec.get("columns"):
            errors.append("A table visual requires at least one column.")
    elif len(nodes) < 2:
        errors.append("At least two nodes are required for a diagram.")

    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"Node {index} must be an object.")
            continue
        node_id = node.get("id")
        label = node.get("label")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"Node {index} needs a non-empty id.")
            continue
        if node_id in seen:
            errors.append(f"Duplicate node id {node_id!r}.")
        seen.add(node_id)
        if not isinstance(label, str) or not label.strip():
            errors.append(f"Node {node_id!r} needs a non-empty label.")
        elif len(label) > MAX_LABEL_CHARS:
            errors.append(f"Node {node_id!r} label exceeds {MAX_LABEL_CHARS} characters.")
        value = node.get("value")
        if kind in DATA_KINDS:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"Node {node_id!r} requires a numeric value for a {kind}.")
        elif value is not None and not isinstance(value, (int, float)):
            errors.append(f"Node {node_id!r} value must be numeric when present.")

    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"Edge {index} must be an object.")
            continue
        source = edge.get("source")
        target = edge.get("target")
        if source not in seen or target not in seen:
            errors.append(f"Edge {index} references an unknown node ({source!r} -> {target!r}).")
        if source == target:
            warnings.append(f"Edge {index} is a self-loop.")

    if kind in {"tree", "network", "er_diagram", "uml_class"} and not edges and len(nodes) > 1:
        warnings.append("Nodes are present without relationships; the diagram may be unclear.")
    if len(nodes) > 12:
        warnings.append("More than 12 nodes may reduce legibility when rendered.")

    return {"valid": not errors, "errors": errors, "warnings": warnings, "kind": kind, "node_count": len(nodes), "edge_count": len(edges)}


# --------------------------------------------------------------------------------------
# Deterministic SVG rendering
# --------------------------------------------------------------------------------------

_NODE_W = 260
_NODE_H = 62
_GAP_X = 40
_GAP_Y = 34
_PAD = 28
_FONT = "font-family='Segoe UI, Helvetica, Arial, sans-serif'"


def _wrap(label: str, width: int = _LABEL_WRAP_CHARS) -> list[str]:
    words = label.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:4]


def _text_block(x: float, y: float, label: str, *, size: int = 13, anchor: str = "middle", weight: str = "400") -> str:
    lines = _wrap(label)
    total = len(lines)
    spans = []
    for index, line in enumerate(lines):
        offset = (index - (total - 1) / 2) * (size + 3)
        spans.append(
            f"<tspan x='{x:.1f}' dy='{offset:.1f}'>{html.escape(line)}</tspan>"
        )
    return (
        f"<text x='{x:.1f}' y='{y:.1f}' {_FONT} font-size='{size}' font-weight='{weight}' "
        f"fill='#0f172a' text-anchor='{anchor}'>" + "".join(spans) + "</text>"
    )


def _arrow_defs() -> str:
    return (
        "<defs><marker id='arrow' viewBox='0 0 10 10' refX='9' refY='5' "
        "markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
        "<path d='M 0 0 L 10 5 L 0 10 z' fill='#334155'/></marker></defs>"
    )


def _node_box(cx: float, cy: float, label: str, *, fill: str = "#eef2ff", stroke: str = "#4f46e5") -> str:
    x = cx - _NODE_W / 2
    y = cy - _NODE_H / 2
    return (
        f"<rect x='{x:.1f}' y='{y:.1f}' width='{_NODE_W}' height='{_NODE_H}' rx='10' "
        f"fill='{fill}' stroke='{stroke}' stroke-width='1.6'/>"
        + _text_block(cx, cy + 4, label)
    )


def _edge_line(x1: float, y1: float, x2: float, y2: float, label: str | None = None) -> str:
    markup = (
        f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
        "stroke='#334155' stroke-width='1.6' marker-end='url(#arrow)'/>"
    )
    if label:
        markup += _text_block((x1 + x2) / 2, (y1 + y2) / 2 - 6, label, size=11)
    return markup


def _layered_positions(nodes: Sequence[dict[str, Any]], edges: Sequence[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """Assign depth by longest path from roots, then place each layer in a row."""
    parents: dict[str, set[str]] = {node["id"]: set() for node in nodes}
    for edge in edges:
        if edge["target"] in parents:
            parents[edge["target"]].add(edge["source"])
    depth: dict[str, int] = {}

    def resolve(node_id: str, guard: frozenset[str]) -> int:
        if node_id in depth:
            return depth[node_id]
        if node_id in guard:
            return 0
        incoming = parents.get(node_id, set())
        value = 0 if not incoming else 1 + max(resolve(parent, guard | {node_id}) for parent in incoming)
        depth[node_id] = value
        return value

    for node in nodes:
        resolve(node["id"], frozenset())

    rows: dict[int, list[str]] = {}
    for node in nodes:
        rows.setdefault(depth.get(node["id"], 0), []).append(node["id"])

    positions: dict[str, tuple[float, float]] = {}
    for row_index, depth_key in enumerate(sorted(rows)):
        row = rows[depth_key]
        width = len(row) * _NODE_W + max(0, len(row) - 1) * _GAP_X
        start_x = _PAD + _NODE_W / 2 + max(0.0, (1000 - 2 * _PAD - width) / 2)
        for column, node_id in enumerate(row):
            cx = start_x + column * (_NODE_W + _GAP_X)
            cy = _PAD + _NODE_H / 2 + row_index * (_NODE_H + _GAP_Y)
            positions[node_id] = (cx, cy)
    return positions


def _render_graph(spec: dict[str, Any]) -> tuple[str, float, float]:
    nodes = spec["nodes"]
    edges = spec.get("edges") or []
    positions = _layered_positions(nodes, edges)
    height = _PAD * 2 + max(y for _, y in positions.values()) + _NODE_H / 2
    width = 1000.0
    parts = [_arrow_defs()]
    for edge in edges:
        sx, sy = positions[edge["source"]]
        tx, ty = positions[edge["target"]]
        parts.append(_edge_line(sx, sy + _NODE_H / 2, tx, ty - _NODE_H / 2, edge.get("label")))
    for node in nodes:
        cx, cy = positions[node["id"]]
        parts.append(_node_box(cx, cy, node["label"]))
    return "".join(parts), width, height


def _render_network(spec: dict[str, Any]) -> tuple[str, float, float]:
    import math

    nodes = spec["nodes"]
    edges = spec.get("edges") or []
    count = max(1, len(nodes))
    radius = max(180.0, count * 34.0)
    cx0, cy0 = radius + _PAD + _NODE_W / 2, radius + _PAD + _NODE_H / 2
    positions = {
        node["id"]: (
            cx0 + radius * math.cos(2 * math.pi * index / count - math.pi / 2),
            cy0 + radius * math.sin(2 * math.pi * index / count - math.pi / 2),
        )
        for index, node in enumerate(nodes)
    }
    parts = [_arrow_defs()]
    for edge in edges:
        sx, sy = positions[edge["source"]]
        tx, ty = positions[edge["target"]]
        parts.append(_edge_line(sx, sy, tx, ty, edge.get("label")))
    for node in nodes:
        cx, cy = positions[node["id"]]
        parts.append(_node_box(cx, cy, node["label"], fill="#ecfeff", stroke="#0891b2"))
    return "".join(parts), (cx0 + radius + _NODE_W / 2 + _PAD), (cy0 + radius + _NODE_H / 2 + _PAD)


def _render_chart(spec: dict[str, Any], *, line: bool) -> tuple[str, float, float]:
    nodes = spec["nodes"]
    values = [float(node.get("value") or 0) for node in nodes]
    peak = max(values) if values else 1.0
    peak = peak if peak > 0 else 1.0
    chart_h = 320.0
    slot = 110.0
    width = _PAD * 2 + slot * len(nodes)
    baseline = _PAD + chart_h
    parts = [
        f"<line x1='{_PAD}' y1='{baseline}' x2='{width - _PAD}' y2='{baseline}' stroke='#334155' stroke-width='1.6'/>",
        f"<line x1='{_PAD}' y1='{_PAD}' x2='{_PAD}' y2='{baseline}' stroke='#334155' stroke-width='1.6'/>",
    ]
    if line:
        points = []
        for index, node in enumerate(nodes):
            x = _PAD + slot * index + slot / 2
            y = baseline - (float(node.get("value") or 0) / peak) * chart_h
            points.append(f"{x:.1f},{y:.1f}")
        parts.append(f"<polyline points='{' '.join(points)}' fill='none' stroke='#0f766e' stroke-width='2.4'/>")
        for index, node in enumerate(nodes):
            x = _PAD + slot * index + slot / 2
            y = baseline - (float(node.get("value") or 0) / peak) * chart_h
            parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4' fill='#0f766e'/>")
            parts.append(_text_block(x, baseline + 18, node["label"], size=11))
            parts.append(_text_block(x, y - 12, f"{node.get('value')}", size=11, weight="600"))
    else:
        bar_w = slot * 0.55
        for index, node in enumerate(nodes):
            value = float(node.get("value") or 0)
            bar_h = (value / peak) * chart_h
            x = _PAD + slot * index + (slot - bar_w) / 2
            parts.append(
                f"<rect x='{x:.1f}' y='{baseline - bar_h:.1f}' width='{bar_w:.1f}' height='{bar_h:.1f}' "
                "fill='#6366f1' rx='4'/>"
            )
            parts.append(_text_block(x + bar_w / 2, baseline - bar_h - 12, f"{node.get('value')}", size=11, weight="600"))
            parts.append(_text_block(x + bar_w / 2, baseline + 18, node["label"], size=11))
    return "".join(parts), width, baseline + 40


def _render_table(spec: dict[str, Any]) -> tuple[str, float, float]:
    columns = [str(column) for column in spec.get("columns") or []]
    rows = [[str(cell) for cell in row] for row in spec.get("rows") or []]
    col_w = 240.0
    row_h = 44.0
    width = _PAD * 2 + col_w * len(columns)
    height = _PAD * 2 + row_h * (len(rows) + 1)
    parts = []
    for column_index, column in enumerate(columns):
        x = _PAD + column_index * col_w
        parts.append(f"<rect x='{x:.1f}' y='{_PAD}' width='{col_w}' height='{row_h}' fill='#e0e7ff' stroke='#4f46e5'/>")
        parts.append(_text_block(x + col_w / 2, _PAD + row_h / 2 + 4, column, size=12, weight="600"))
    for row_index, row in enumerate(rows):
        y = _PAD + row_h * (row_index + 1)
        for column_index in range(len(columns)):
            x = _PAD + column_index * col_w
            cell = row[column_index] if column_index < len(row) else ""
            parts.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{col_w}' height='{row_h}' fill='#ffffff' stroke='#94a3b8'/>")
            parts.append(_text_block(x + col_w / 2, y + row_h / 2 + 4, cell, size=11))
    return "".join(parts), width, height


def render_svg(spec: dict[str, object]) -> str:
    """Render a validated specification to a standalone, script-free SVG document."""
    report = validate_spec(spec)
    if not report["valid"]:
        raise VisualSpecInvalid("; ".join(report["errors"]))
    kind = str(spec["kind"])
    if kind == "network":
        body, width, height = _render_network(spec)
    elif kind == "bar_chart":
        body, width, height = _render_chart(spec, line=False)
    elif kind == "line_chart":
        body, width, height = _render_chart(spec, line=True)
    elif kind == "table":
        body, width, height = _render_table(spec)
    else:
        body, width, height = _render_graph(spec)

    title = html.escape(str(spec["title"]))
    description = html.escape(build_alt_text(spec))
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' role='img' viewBox='0 0 {width:.0f} {height:.0f}' "
        f"width='{width:.0f}' height='{height:.0f}'><title>{title}</title><desc>{description}</desc>"
        f"<rect width='100%' height='100%' fill='#ffffff'/>{body}</svg>"
    )
    _assert_svg_safe(svg)
    return svg


def build_alt_text(spec: dict[str, object]) -> str:
    """Produce accessible alternative text describing the diagram's content."""
    kind = _kind_title(str(spec.get("kind") or ""))
    labels = [str(node.get("label", "")).strip() for node in (spec.get("nodes") or [])]
    labels = [label for label in labels if label]
    if spec.get("kind") == "table":
        columns = [str(column) for column in spec.get("columns") or []]
        return f"{spec.get('title', 'Table')}. A structured table with columns: {', '.join(columns)}."
    summary = "; ".join(labels[:12])
    if len(labels) > 12:
        summary += f"; and {len(labels) - 12} more"
    return f"{spec.get('title', 'Diagram')}. A {kind} containing: {summary}."


def _assert_svg_safe(svg: str) -> None:
    lowered = svg.casefold()
    for token in _FORBIDDEN_SVG:
        if token in lowered:
            raise VisualSpecInvalid(f"Rendered SVG contains a forbidden construct: {token}.")


def requirement_summary(determinations: Iterable[RequirementDetermination]) -> dict[str, int]:
    counts = {"essential": 0, "beneficial": 0, "unnecessary": 0}
    for item in determinations:
        counts[item.level] = counts.get(item.level, 0) + 1
    return counts
