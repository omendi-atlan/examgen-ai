"""Unit coverage for the deterministic visual intelligence service."""

import pytest
from app.services.visual_intelligence import (
    VisualSpecInvalid,
    build_alt_text,
    build_auto_draft_spec,
    determine_requirement,
    render_svg,
    validate_spec,
)


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("Network topology and routing", "essential"),
        ("Database normalisation and foreign keys", "essential"),
        ("Algorithm flowchart design", "beneficial"),
        ("Introduction to accounting", "unnecessary"),
    ],
)
def test_requirement_levels_are_deterministic(topic, expected):
    first = determine_requirement("topic-1", topic)
    second = determine_requirement("topic-1", topic)
    assert first.level == expected
    # Same input must always yield the same verdict and evidence.
    assert first.level == second.level
    assert first.recommended_kind == second.recommended_kind
    assert first.signals == second.signals
    if expected == "unnecessary":
        assert first.recommended_kind is None
    else:
        assert first.rationale


def test_auto_draft_builds_structural_diagram_from_outcomes():
    spec = build_auto_draft_spec(
        title="Routing steps",
        kind="flowchart",
        outcome_labels=["Inspect the header", "Select the next hop", "Forward the packet"],
    )
    assert spec["provenance"]["source"] == "auto_draft"
    assert len(spec["nodes"]) == 3
    assert len(spec["edges"]) == 2
    assert validate_spec(spec)["valid"] is True
    svg = render_svg(spec)
    assert svg.startswith("<svg") and "Inspect the header" in svg


def test_auto_draft_refuses_data_bearing_charts():
    with pytest.raises(VisualSpecInvalid):
        build_auto_draft_spec(title="Throughput", kind="bar_chart", outcome_labels=["One"])


def test_auto_draft_requires_at_least_one_outcome():
    with pytest.raises(VisualSpecInvalid):
        build_auto_draft_spec(title="Empty", kind="flowchart", outcome_labels=["   "])


def test_validate_spec_reports_actionable_errors():
    report = validate_spec(
        {
            "title": "Broken",
            "kind": "flowchart",
            "nodes": [{"id": "a", "label": "Only one"}],
            "edges": [{"source": "a", "target": "missing"}],
        }
    )
    assert report["valid"] is False
    assert any("two nodes" in error for error in report["errors"])
    assert any("unknown node" in error for error in report["errors"])


def test_charts_require_numeric_values():
    report = validate_spec(
        {
            "title": "Trend",
            "kind": "line_chart",
            "nodes": [{"id": "a", "label": "Week 1"}, {"id": "b", "label": "Week 2", "value": 4}],
            "edges": [],
        }
    )
    assert report["valid"] is False
    assert any("numeric value" in error for error in report["errors"])


def test_render_is_script_free_and_accessible():
    spec = {
        "title": "Class hierarchy",
        "kind": "uml_class",
        "nodes": [
            {"id": "a", "label": "Animal"},
            {"id": "b", "label": "Dog"},
        ],
        "edges": [{"source": "b", "target": "a", "label": "inherits"}],
    }
    svg = render_svg(spec)
    lowered = svg.casefold()
    for token in ("<script", "javascript:", "onload=", "<foreignobject"):
        assert token not in lowered
    assert "<title>" in svg and "<desc>" in svg
    assert "Animal" in build_alt_text(spec)


def test_table_visual_renders_columns():
    spec = {
        "title": "Comparison",
        "kind": "table",
        "columns": ["Approach", "Complexity"],
        "rows": [["Linear search", "O(n)"]],
        "nodes": [],
        "edges": [],
    }
    assert validate_spec(spec)["valid"] is True
    svg = render_svg(spec)
    assert "Complexity" in svg and "O(n)" in svg
