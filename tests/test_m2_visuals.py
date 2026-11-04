"""Milestone 2 — visual requirements assessment, construction, approval, blueprint."""

from __future__ import annotations

import io

from .conftest import make_text_document

# Coursework that is unambiguously diagram-dependent.
DIAGRAM_HEAVY = b"""Database Systems - Entity Relationship Modelling

Chapter 1. Entity Relationship Diagrams
An entity relationship diagram is a visual representation of the entities in a
database and the relationships between them. Each entity has a primary key that
uniquely identifies every record. A foreign key is an attribute that creates a
link between two tables and enforces referential integrity.
The cardinality of a relationship describes how many instances of one entity
relate to instances of another entity. One to many cardinality is the most common
relationship type in a normalised schema.
Normalisation is the process of organising the columns and tables of a relational
database to minimise redundancy. First normal form eliminates repeating groups.
Second normal form removes partial dependencies. Third normal form removes
transitive dependencies.
Draw the entity relationship diagram for a student records system and label the
cardinality of every relationship.

Chapter 2. Network Topology
A network topology describes the arrangement of the elements of a communication
network. The star topology connects every device to a central switch. The mesh
topology connects every device to every other device.
A firewall filters traffic between the internal network and the internet. A router
forwards packets between subnets and a switch forwards frames within a subnet.
Draw the network topology diagram for a three tier architecture and label each
device.

Chapter 3. UML Modelling
A UML class diagram shows the classes in a system, their attributes and their
operations. An association shows a relationship between two classes.
A sequence diagram shows the interaction between objects over time.
Draw a UML class diagram for the order processing module and label the
multiplicities on each association.
"""


def _workspace(client, auth, name="Database Systems"):
    response = client.post("/api/workspaces", json={
        "name": name, "code": "CS310", "module": "Databases"},
        headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, auth, workspace_id, filename, content):
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_visual_requirement_is_assessed_before_blueprint(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "er.txt", DIAGRAM_HEAVY)
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)

    topics = client.get(f"/api/workspaces/{workspace['id']}/topics", headers=auth).json()
    assert topics
    visual_topics = [t for t in topics if t["needs_visual"] != "unnecessary"]
    assert visual_topics, "diagram-dependent coursework must be flagged"
    assert any(t["needs_visual"] == "essential" for t in visual_topics)
    assert all(t["visual_rationale"] for t in visual_topics)


def test_visual_generation_produces_editable_versioned_assets(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "er.txt", DIAGRAM_HEAVY)
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    proposed = client.post(f"/api/workspaces/{workspace['id']}/visuals/propose", headers=auth).json()
    assert proposed["created"] >= 1

    visuals = client.get(f"/api/workspaces/{workspace['id']}/visuals", headers=auth).json()
    assert visuals
    for visual in visuals:
        assert visual["status"] == "proposed"
        assert visual["version"] == 1
        assert visual["svg"].startswith("<svg")
        assert "viewBox" in visual["svg"]          # editable vector, not a raster
        assert visual["labels"]
        assert visual["intended_use"]


def test_visual_approval_is_required_and_versioned(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "er.txt", DIAGRAM_HEAVY)
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    client.post(f"/api/workspaces/{workspace['id']}/visuals/propose", headers=auth)
    visual = client.get(f"/api/workspaces/{workspace['id']}/visuals", headers=auth).json()[0]

    approved = client.post(
        f"/api/workspaces/{workspace['id']}/visuals/{visual['id']}/decision",
        json={"decision": "approve"}, headers=auth).json()
    assert approved["status"] == "approved"

    revised = client.post(
        f"/api/workspaces/{workspace['id']}/visuals/{visual['id']}/revise",
        json={"labels": ["Student", "Course", "Enrolment"]}, headers=auth).json()
    assert revised["version"] == 2
    # A revision invalidates the previous approval and must be re-approved.
    assert revised["status"] == "proposed"
    assert "Student" in revised["svg"]


def test_visual_assets_are_isolated_between_workspaces(client, auth):
    first = _workspace(client, auth, "Databases A")
    second = _workspace(client, auth, "Databases B")
    _upload(client, auth, first["id"], "er.txt", DIAGRAM_HEAVY)
    client.post(f"/api/workspaces/{first['id']}/classify", headers=auth)
    client.post(f"/api/workspaces/{first['id']}/visuals/propose", headers=auth)

    assert client.get(f"/api/workspaces/{second['id']}/visuals", headers=auth).json() == []
    assert client.get(f"/api/workspaces/{first['id']}/visuals", headers=auth).json()


def test_blueprint_validation_enforces_marks_and_duration(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "er.txt", DIAGRAM_HEAVY)
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)

    # Impossible: 200 marks in 10 minutes.
    response = client.post(f"/api/workspaces/{workspace['id']}/blueprints", json={
        "title": "Impossible paper", "duration_minutes": 10, "total_marks": 200,
        "question_count": 20}, headers=auth)
    assert response.status_code == 201
    blueprint = response.json()
    assert blueprint["is_valid"] is False
    assert any("minutes per mark" in issue for issue in blueprint["validation"]["issues"])

    # Feasible blueprint.
    valid = client.post(f"/api/workspaces/{workspace['id']}/blueprints", json={
        "title": "Databases mid-term", "duration_minutes": 90, "total_marks": 60,
        "question_count": 10}, headers=auth).json()
    assert valid["is_valid"] is True
    assert valid["validation"]["minutes_per_mark"] >= 0.6


def test_blueprint_validation_reports_insufficient_material(client, auth):
    workspace = _workspace(client, auth, "Barely Any Material")
    _upload(client, auth, workspace["id"], "tiny.txt", b"Chapter 1. A very short note.")
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)

    blueprint = client.post(f"/api/workspaces/{workspace['id']}/blueprints", json={
        "title": "Thin paper", "duration_minutes": 120, "total_marks": 50,
        "question_count": 10}, headers=auth).json()
    assert "numerical" in blueprint["validation"]["insufficient_question_types"] or \
           "extended_response" in blueprint["validation"]["insufficient_question_types"]


def test_no_visuals_are_proposed_when_unnecessary(client, auth):
    workspace = _workspace(client, auth, "Pure Theory")
    # Purely definitional material with no diagram, graph or topology references.
    _upload(client, auth, workspace["id"], "ethics.txt", b"""Professional Ethics - Lecture Notes

Chapter 1. Introduction
Ethics is the branch of philosophy concerned with moral principles and conduct.
Professional ethics refers to the personal and corporate rules that govern
behaviour within a professional context.
Integrity is defined as the quality of being honest and having strong moral
principles. Accountability means accepting responsibility for one's actions.
Confidentiality is the duty to protect information entrusted by a client.
Informed consent means a client agrees to a course of action having understood
the implications.
Chapter 2. Codes of Conduct
A code of conduct is a set of rules outlining the responsibilities of an
organisation. A conflict of interest arises when a personal interest could
improperly influence professional judgement. Whistleblowing means reporting
unlawful or unethical conduct within an organisation.
Chapter 3. Ethical Reasoning
Consequentialism judges actions by their outcomes. Deontology judges actions by
rules and duties regardless of outcome. Virtue ethics focuses on the character
of the moral agent rather than the act itself.
""")
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    client.post(f"/api/workspaces/{workspace['id']}/visuals/propose", headers=auth)
    visuals = client.get(f"/api/workspaces/{workspace['id']}/visuals", headers=auth).json()
    # No visual requirement exists, so nothing is fabricated.
    assert visuals == []


def test_graph_references_produce_a_graph_visual(client, auth):
    workspace = _workspace(client, auth, "Performance Analysis")
    _upload(client, auth, workspace["id"], "graphs.txt", b"""Chapter 1. Plotting Results
The running time of an algorithm can be plotted on a graph against the input
size. The x axis shows the input size and the y axis shows the running time.
The gradient of the curve indicates the rate of growth. A histogram of the
scatter data can be used to show the distribution of the measurements.
Plot the graph for each function and determine the gradient of the curve.
""")
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    client.post(f"/api/workspaces/{workspace['id']}/visuals/propose", headers=auth)
    visuals = client.get(f"/api/workspaces/{workspace['id']}/visuals", headers=auth).json()
    assert visuals, "graph-based material must produce a graph asset"
    assert any(v["diagram_type"] == "graph" for v in visuals)
