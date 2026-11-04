"""Visual requirements assessment, specification and diagram construction.

Diagrams are constructed deterministically as **editable SVG** rather than
raster images. For exam content that depends on precise symbols, relationships
and labels, vector output keeps text selectable, scales losslessly and can be
annotated or corrected by the student. Every asset is versioned and requires
explicit student approval before a question may reference it.

Visual requirement classification happens *before* blueprint generation so the
examination can be designed around approved assets.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

PALETTE = {
    "bg": "#ffffff",
    "ink": "#0f172a",
    "muted": "#64748b",
    "line": "#334155",
    "accent": "#2563eb",
    "accent2": "#0ea5e9",
    "accent3": "#7c3aed",
    "soft": "#e0e7ff",
    "soft2": "#dcfce7",
    "soft3": "#fef3c7",
    "soft4": "#fee2e2",
    "soft5": "#e2e8f0",
}
FONT = "Inter, Segoe UI, system-ui, -apple-system, Arial, sans-serif"

DIAGRAM_TYPES = [
    "architecture", "network_topology", "uml", "er_diagram", "flowchart",
    "process", "graph", "circuit", "scientific", "table", "project_network",
    "annotated",
]

TYPE_TITLES = {
    "architecture": "System Architecture Diagram",
    "network_topology": "Network Topology Diagram",
    "uml": "UML Class Diagram",
    "er_diagram": "Entity Relationship Diagram",
    "flowchart": "Flowchart",
    "process": "Process Diagram",
    "graph": "Mathematical Graph",
    "circuit": "Circuit Diagram",
    "scientific": "Scientific Illustration",
    "table": "Structured Data Table",
    "project_network": "Project Network Diagram",
    "annotated": "Annotated Diagram",
}


@dataclass
class VisualSpec:
    key: str
    title: str
    diagram_type: str
    topic_id: str | None = None
    learning_outcome_id: str | None = None
    requirement: str = "beneficial"
    labels: list[str] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    intended_use: str = ""
    nodes: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _wrap(text: str, width: int = 18, max_lines: int = 3) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if not lines:
        lines = [str(text)[:width]]
    return lines


def _svg(width: int, height: int, body: str, title: str, desc: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img" aria-labelledby="vtitle vdesc" '
        f'font-family="{FONT}">'
        f'<title id="vtitle">{_esc(title)}</title>'
        f'<desc id="vdesc">{_esc(desc)}</desc>'
        f'<defs>'
        f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{PALETTE["line"]}"/></marker>'
        f'<marker id="arrow-accent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{PALETTE["accent"]}"/></marker>'
        f'</defs>'
        f'<rect width="{width}" height="{height}" fill="{PALETTE["bg"]}"/>'
        f'{body}</svg>'
    )


def _box(x: float, y: float, w: float, h: float, text: str, fill: str,
         stroke: str | None = None, radius: int = 8, font_size: int = 13,
         bold: bool = False, text_color: str | None = None) -> str:
    stroke = stroke or PALETTE["line"]
    text_color = text_color or PALETTE["ink"]
    lines = _wrap(text, max(8, int(w / 8)), max(1, int(h / 18)))
    start_y = y + h / 2 - (len(lines) - 1) * (font_size + 2) / 2 + font_size / 3
    tspans = "".join(
        f'<tspan x="{x + w / 2}" y="{start_y + i * (font_size + 2)}">{_esc(line)}</tspan>'
        for i, line in enumerate(lines))
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.5"/>'
        f'<text x="{x + w / 2}" y="{start_y}" text-anchor="middle" '
        f'font-size="{font_size}" fill="{text_color}"'
        f'{" font-weight=\"600\"" if bold else ""}>{tspans}</text>'
    )


def _arrow(x1: float, y1: float, x2: float, y2: float, label: str = "",
           dashed: bool = False, accent: bool = False) -> str:
    marker = "arrow-accent" if accent else "arrow"
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    color = PALETTE["accent"] if accent else PALETTE["line"]
    out = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
           f'stroke-width="1.8"{dash} marker-end="url(#{marker})"/>')
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        out += (f'<rect x="{mx - len(label) * 3.6 - 4}" y="{my - 11}" '
                f'width="{len(label) * 7.2 + 8}" height="17" rx="4" fill="{PALETTE["bg"]}" '
                f'opacity="0.92"/>'
                f'<text x="{mx}" y="{my + 2}" text-anchor="middle" font-size="11" '
                f'fill="{PALETTE["muted"]}">{_esc(label)}</text>')
    return out


def _title_block(title: str, subtitle: str, width: int) -> str:
    return (
        f'<text x="20" y="28" font-size="16" font-weight="700" '
        f'fill="{PALETTE["ink"]}">{_esc(title)}</text>'
        f'<text x="20" y="46" font-size="11" fill="{PALETTE["muted"]}">{_esc(subtitle)}</text>'
    )


def _default_nodes(spec: VisualSpec) -> list[dict]:
    if spec.nodes:
        return spec.nodes
    return [{"label": label} for label in (spec.labels or [])]


def build_architecture(spec: VisualSpec) -> str:
    nodes = _default_nodes(spec) or [{"label": "Client"}, {"label": "Application"},
                                     {"label": "Data Store"}]
    width, height = 760, max(300, 90 + len(nodes) * 60)
    body = _title_block(spec.title, "System architecture — component relationships", width)
    y = 70
    colors = [PALETTE["soft"], PALETTE["soft2"], PALETTE["soft3"], PALETTE["soft4"]]
    for i, node in enumerate(nodes):
        label = node.get("label", f"Component {i + 1}")
        body += _box(60, y, 300, 44, label, colors[i % len(colors)])
        if i < len(nodes) - 1:
            body += _arrow(210, y + 44, 210, y + 60, node.get("edge", "uses"))
        y += 60
    body += f'<text x="620" y="90" font-size="11" fill="{PALETTE["muted"]}" ' \
            f'text-anchor="middle">Edges are directed</text>'
    return _svg(width, height, body, spec.title, "System architecture diagram")


def build_network(spec: VisualSpec) -> str:
    nodes = _default_nodes(spec) or [{"label": "Internet"}, {"label": "Firewall"},
                                     {"label": "Router"}, {"label": "Switch"},
                                     {"label": "Clients"}]
    width, height = 760, max(320, 100 + len(nodes) * 46)
    body = _title_block(spec.title, "Network topology — device and link layout", width)
    y = 76
    for i, node in enumerate(nodes):
        fill = PALETTE["soft2"] if i in (0, len(nodes) - 1) else PALETTE["soft"]
        body += _box(80, y, 240, 36, node.get("label", f"Device {i + 1}"), fill)
        body += _box(360, y + 4, 300, 28, node.get("detail", "link / interface"),
                     PALETTE["soft5"], font_size=11)
        if i < len(nodes) - 1:
            body += _arrow(200, y + 36, 200, y + 46)
        y += 46
    return _svg(width, height, body, spec.title, "Network topology diagram")


def build_uml(spec: VisualSpec) -> str:
    classes = spec.nodes or [
        {"label": "Entity", "attrs": ["- id: UUID", "- name: String"],
         "methods": ["+ save(): void", "+ validate(): bool"]},
    ]
    width = 240 * max(1, min(len(classes), 3)) + 60
    rows = (len(classes) + 2) // 3
    height = 110 + rows * 190
    body = _title_block(spec.title, "UML class diagram — attributes and operations", width)
    for i, cls in enumerate(classes):
        col, row = i % 3, i // 3
        x = 30 + col * 240
        y = 70 + row * 190
        attrs = cls.get("attrs") or ["- attribute: Type"]
        methods = cls.get("methods") or ["+ operation(): Type"]
        h = 60 + len(attrs) * 18 + len(methods) * 18
        body += (f'<rect x="{x}" y="{y}" width="210" height="{h}" rx="6" '
                 f'fill="{PALETTE["bg"]}" stroke="{PALETTE["line"]}" stroke-width="1.5"/>')
        body += (f'<rect x="{x}" y="{y}" width="210" height="30" rx="6" '
                 f'fill="{PALETTE["soft"]}" stroke="{PALETTE["line"]}" stroke-width="1.5"/>')
        body += (f'<text x="{x + 105}" y="{y + 20}" text-anchor="middle" font-size="13" '
                 f'font-weight="600" fill="{PALETTE["ink"]}">{_esc(cls.get("label", "Class"))}</text>')
        ty = y + 50
        for attr in attrs:
            body += (f'<text x="{x + 12}" y="{ty}" font-size="11" '
                     f'fill="{PALETTE["ink"]}">{_esc(attr)}</text>')
            ty += 18
        body += (f'<line x1="{x}" y1="{ty - 6}" x2="{x + 210}" y2="{ty - 6}" '
                 f'stroke="{PALETTE["line"]}" stroke-width="1"/>')
        ty += 10
        for method in methods:
            body += (f'<text x="{x + 12}" y="{ty}" font-size="11" '
                     f'fill="{PALETTE["muted"]}">{_esc(method)}</text>')
            ty += 18
    return _svg(width, height, body, spec.title, "UML class diagram")


def build_er(spec: VisualSpec) -> str:
    entities = spec.nodes or [
        {"label": "CUSTOMER", "attrs": ["PK customer_id", "name", "email"]},
        {"label": "ORDER", "attrs": ["PK order_id", "FK customer_id", "total"]},
    ]
    width = 260 * max(1, min(len(entities), 3)) + 60
    rows = (len(entities) + 2) // 3
    height = 110 + rows * 170
    body = _title_block(spec.title, "Entity relationship diagram — keys and relationships", width)
    for i, entity in enumerate(entities):
        col, row = i % 3, i // 3
        x = 30 + col * 260
        y = 70 + row * 170
        attrs = entity.get("attrs") or ["PK id", "attribute"]
        h = 40 + len(attrs) * 18
        body += (f'<rect x="{x}" y="{y}" width="230" height="{h}" rx="4" '
                 f'fill="{PALETTE["bg"]}" stroke="{PALETTE["line"]}" stroke-width="1.5"/>')
        body += (f'<rect x="{x}" y="{y}" width="230" height="28" rx="4" '
                 f'fill="{PALETTE["soft3"]}" stroke="{PALETTE["line"]}" stroke-width="1.5"/>')
        body += (f'<text x="{x + 115}" y="{y + 19}" text-anchor="middle" font-size="12" '
                 f'font-weight="700" fill="{PALETTE["ink"]}">{_esc(entity.get("label", "ENTITY"))}</text>')
        ty = y + 46
        for attr in attrs:
            style = "font-weight=\"600\"" if str(attr).startswith("PK") else ""
            body += (f'<text x="{x + 12}" y="{ty}" font-size="11" {style} '
                     f'fill="{PALETTE["ink"]}">{_esc(attr)}</text>')
            ty += 18
        if col < 2 and i < len(entities) - 1:
            body += _arrow(x + 230, y + h / 2, x + 258, y + h / 2, "1..*", accent=True)
    return _svg(width, height, body, spec.title, "Entity relationship diagram")


def build_flowchart(spec: VisualSpec) -> str:
    steps = _default_nodes(spec) or [
        {"label": "Start", "kind": "start"}, {"label": "Read input"},
        {"label": "Condition?", "kind": "decision"},
        {"label": "Process", "kind": "process"}, {"label": "End", "kind": "end"},
    ]
    width, height = 640, 90 + len(steps) * 74
    body = _title_block(spec.title, "Flowchart — control flow and decisions", width)
    y = 70
    for i, step in enumerate(steps):
        kind = step.get("kind", "process")
        label = step.get("label", f"Step {i + 1}")
        if kind in {"start", "end"}:
            body += _box(180, y, 240, 40, label, PALETTE["soft2"], radius=20, bold=True)
        elif kind == "decision":
            body += (f'<polygon points="300,{y} 420,{y + 26} 300,{y + 52} 180,{y + 26}" '
                     f'fill="{PALETTE["soft3"]}" stroke="{PALETTE["line"]}" stroke-width="1.5"/>'
                     f'<text x="300" y="{y + 30}" text-anchor="middle" font-size="12" '
                     f'fill="{PALETTE["ink"]}">{_esc(label)}</text>')
        else:
            body += _box(180, y, 240, 40, label, PALETTE["soft"])
        if i < len(steps) - 1:
            body += _arrow(300, y + (52 if kind == "decision" else 40), 300, y + 74)
        y += 74
    return _svg(width, height, body, spec.title, "Flowchart diagram")


def build_graph(spec: VisualSpec) -> str:
    width, height = 640, 400
    ox, oy = 70, 340
    gw, gh = 500, 280
    body = _title_block(spec.title, "Mathematical graph — axes, curve and key points", width)
    body += (f'<line x1="{ox}" y1="{oy}" x2="{ox + gw}" y2="{oy}" stroke="{PALETTE["line"]}" '
             f'stroke-width="1.5" marker-end="url(#arrow)"/>')
    body += (f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy - gh}" stroke="{PALETTE["line"]}" '
             f'stroke-width="1.5" marker-end="url(#arrow)"/>')
    body += (f'<text x="{ox + gw + 6}" y="{oy + 4}" font-size="12" fill="{PALETTE["ink"]}">x</text>')
    body += (f'<text x="{ox - 4}" y="{oy - gh - 8}" font-size="12" fill="{PALETTE["ink"]}">y</text>')
    points = spec.meta.get("points") or []
    if points:
        coords = " ".join(f"{ox + float(px) * gw},{oy - float(py) * gh}" for px, py in points)
        body += (f'<polyline points="{coords}" fill="none" stroke="{PALETTE["accent"]}" '
                 f'stroke-width="2.5"/>')
        for i, (px, py) in enumerate(points):
            cx, cy = ox + float(px) * gw, oy - float(py) * gh
            body += (f'<circle cx="{cx}" cy="{cy}" r="4" fill="{PALETTE["accent"]}"/>'
                     f'<text x="{cx + 8}" y="{cy - 8}" font-size="11" '
                     f'fill="{PALETTE["muted"]}">P{i + 1}</text>')
    else:
        body += (f'<path d="M {ox} {oy} Q {ox + gw * 0.5} {oy - gh} {ox + gw} {oy - gh * 0.2}" '
                 f'fill="none" stroke="{PALETTE["accent"]}" stroke-width="2.5"/>')
    for i in range(1, 5):
        gx = ox + gw * i / 4
        gy = oy - gh * i / 4
        body += (f'<line x1="{gx}" y1="{oy}" x2="{gx}" y2="{oy + 5}" '
                 f'stroke="{PALETTE["muted"]}"/>'
                 f'<line x1="{ox}" y1="{gy}" x2="{ox - 5}" y2="{gy}" stroke="{PALETTE["muted"]}"/>')
    return _svg(width, height, body, spec.title, "Mathematical graph")


def build_circuit(spec: VisualSpec) -> str:
    width, height = 640, 320
    body = _title_block(spec.title, "Circuit diagram — components and connections", width)
    body += (f'<rect x="90" y="110" width="460" height="120" fill="none" '
             f'stroke="{PALETTE["line"]}" stroke-width="2"/>')
    body += _box(60, 150, 60, 40, "V", PALETTE["soft4"])
    body += _box(300, 88, 90, 26, "R1", PALETTE["soft"], font_size=11)
    body += (f'<rect x="480" y="150" width="60" height="40" rx="4" fill="{PALETTE["soft3"]}" '
             f'stroke="{PALETTE["line"]}" stroke-width="1.5"/>'
             f'<text x="510" y="175" text-anchor="middle" font-size="12" '
             f'fill="{PALETTE["ink"]}">Load</text>')
    body += (f'<circle cx="250" cy="230" r="16" fill="{PALETTE["bg"]}" '
             f'stroke="{PALETTE["line"]}" stroke-width="1.5"/>'
             f'<text x="250" y="235" text-anchor="middle" font-size="12" '
             f'fill="{PALETTE["ink"]}">A</text>')
    for label in spec.labels[:6]:
        body += (f'<text x="90" y="285" font-size="11" fill="{PALETTE["muted"]}">{_esc(label)}</text>')
    return _svg(width, height, body, spec.title, "Circuit diagram")


def build_table(spec: VisualSpec) -> str:
    headers = spec.meta.get("headers") or spec.labels or ["Column A", "Column B", "Column C"]
    rows = spec.meta.get("rows") or [["", "", ""], ["", "", ""]]
    col_w = 190
    width = 40 + col_w * len(headers)
    height = 110 + len(rows) * 30
    body = _title_block(spec.title, "Structured data — read values from the table", width)
    x0, y0 = 20, 62
    for c, head in enumerate(headers):
        body += (f'<rect x="{x0 + c * col_w}" y="{y0}" width="{col_w}" height="30" '
                 f'fill="{PALETTE["soft"]}" stroke="{PALETTE["line"]}"/>'
                 f'<text x="{x0 + c * col_w + col_w / 2}" y="{y0 + 20}" text-anchor="middle" '
                 f'font-size="12" font-weight="600" fill="{PALETTE["ink"]}">{_esc(head)}</text>')
    for r, row in enumerate(rows):
        for c, cell in enumerate(row[:len(headers)]):
            body += (f'<rect x="{x0 + c * col_w}" y="{y0 + 30 + r * 30}" width="{col_w}" '
                     f'height="30" fill="{PALETTE["bg"]}" stroke="{PALETTE["line"]}"/>'
                     f'<text x="{x0 + c * col_w + col_w / 2}" y="{y0 + 50 + r * 30}" '
                     f'text-anchor="middle" font-size="12" '
                     f'fill="{PALETTE["ink"]}">{_esc(cell)}</text>')
    return _svg(width, height, body, spec.title, "Structured data table")


def build_project_network(spec: VisualSpec) -> str:
    nodes = _default_nodes(spec) or [
        {"label": "A", "detail": "0"}, {"label": "B", "detail": "4"},
        {"label": "C", "detail": "7"}, {"label": "D", "detail": "11"},
    ]
    width, height = 700, 300
    body = _title_block(spec.title, "Project network — activity nodes and durations", width)
    y = 90
    for i, node in enumerate(nodes):
        x = 50 + i * 150
        body += (f'<circle cx="{x + 40}" cy="{y + 40}" r="40" fill="{PALETTE["soft"]}" '
                 f'stroke="{PALETTE["line"]}" stroke-width="1.5"/>')
        body += (f'<text x="{x + 40}" y="{y + 36}" text-anchor="middle" font-size="15" '
                 f'font-weight="700" fill="{PALETTE["ink"]}">{_esc(node.get("label", chr(65 + i)))}</text>')
        body += (f'<text x="{x + 40}" y="{y + 56}" text-anchor="middle" font-size="11" '
                 f'fill="{PALETTE["muted"]}">{_esc(node.get("detail", ""))}</text>')
        if i < len(nodes) - 1:
            body += _arrow(x + 80, y + 40, x + 150, y + 40)
    return _svg(width, height, body, spec.title, "Project network diagram")


def build_scientific(spec: VisualSpec) -> str:
    parts = spec.labels or ["Structure A", "Structure B", "Structure C"]
    width, height = 640, 320
    body = _title_block(spec.title, "Scientific illustration — labelled structures", width)
    positions = [(150, 160, 70), (330, 140, 55), (470, 190, 40)]
    for i, label in enumerate(parts[:3]):
        cx, cy, r = positions[i]
        body += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{PALETTE["soft2"]}" '
                 f'stroke="{PALETTE["line"]}" stroke-width="1.5"/>'
                 f'<circle cx="{cx}" cy="{cy}" r="{max(6, r - 22)}" fill="{PALETTE["soft"]}" '
                 f'stroke="{PALETTE["line"]}"/>')
        body += _arrow(cx, cy - r, cx, cy - r - 22)
        body += (f'<text x="{cx}" y="{cy - r - 30}" text-anchor="middle" font-size="11" '
                 f'fill="{PALETTE["muted"]}">{_esc(label)}</text>')
    return _svg(width, height, body, spec.title, "Scientific illustration")


def build_annotated(spec: VisualSpec) -> str:
    labels = spec.labels or ["Part A", "Part B", "Part C"]
    width, height = 640, 340
    body = _title_block(spec.title, "Annotated diagram — identify the labelled parts", width)
    body += (f'<rect x="200" y="100" width="240" height="160" rx="10" '
             f'fill="{PALETTE["soft"]}" stroke="{PALETTE["line"]}" stroke-width="1.5"/>')
    offsets = [(150, 120), (460, 140), (150, 240), (460, 240)]
    for i, label in enumerate(labels[:4]):
        lx, ly = offsets[i]
        ax = 320 if lx < 320 else 320
        ay = 180
        body += _arrow(lx + (60 if lx < 320 else 0), ly, ax, ay, accent=True)
        body += (f'<text x="{lx}" y="{ly - 10}" text-anchor="middle" font-size="11" '
                 f'fill="{PALETTE["muted"]}">{_esc(label)}</text>')
    return _svg(width, height, body, spec.title, "Annotated diagram")


_BUILDERS = {
    "architecture": build_architecture,
    "network_topology": build_network,
    "uml": build_uml,
    "er_diagram": build_er,
    "flowchart": build_flowchart,
    "process": build_flowchart,
    "graph": build_graph,
    "circuit": build_circuit,
    "scientific": build_scientific,
    "table": build_table,
    "project_network": build_project_network,
    "annotated": build_annotated,
}


def construct(spec: VisualSpec) -> str:
    """Construct an editable SVG for the given specification."""
    builder = _BUILDERS.get(spec.diagram_type, build_annotated)
    return builder(spec)


def infer_spec(key: str, title: str, diagram_type: str, topic_name: str,
               labels: list[str] | None = None, **kwargs) -> VisualSpec:
    labels = labels or _default_labels(diagram_type, topic_name)
    return VisualSpec(
        key=key,
        title=title or TYPE_TITLES.get(diagram_type, "Diagram"),
        diagram_type=diagram_type,
        labels=labels,
        intended_use=kwargs.get("intended_use", ""),
        topic_id=kwargs.get("topic_id"),
        learning_outcome_id=kwargs.get("learning_outcome_id"),
        requirement=kwargs.get("requirement", "beneficial"),
        meta=kwargs.get("meta", {}),
        nodes=kwargs.get("nodes", []),
    )


def _default_labels(diagram_type: str, topic_name: str) -> list[str]:
    topic = topic_name or "the system"
    defaults = {
        "architecture": ["Presentation layer", "Business logic layer",
                         "Data access layer", "External service"],
        "network_topology": ["WAN link", "Edge firewall", "Core router",
                             "Access switch", "Client subnet"],
        "uml": ["Class name", "Attributes", "Operations", "Association"],
        "er_diagram": ["Primary key", "Foreign key", "Cardinality", "Relationship"],
        "flowchart": ["Start", "Input", "Decision", "Process", "End"],
        "process": ["Trigger", "Activity", "Validation", "Outcome"],
        "graph": ["Independent variable", "Dependent variable", "Gradient", "Intercept"],
        "circuit": ["Supply voltage", "Resistance", "Current", "Reference node"],
        "scientific": ["Primary structure", "Secondary structure", "Membrane"],
        "table": ["Identifier", "Measured value", "Derived value"],
        "project_network": ["Activity node", "Duration", "Dependency", "Critical path"],
        "annotated": ["Component A", "Component B", "Component C", "Component D"],
    }
    labels = defaults.get(diagram_type, [f"{topic} part A", f"{topic} part B"])
    return [f"{label}" for label in labels]


def render_preview(spec: VisualSpec) -> str:
    return construct(spec)
