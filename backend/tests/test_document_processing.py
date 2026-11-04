"""Durable document processing and quality-gate unit tests."""

from app.services.document_processing import extraction_quality


def test_quality_gate_flags_sparse_text_for_human_review() -> None:
    report = extraction_quality(
        character_count=35,
        page_count=4,
        segment_count=1,
        status="extracted",
    )
    assert report["outcome"] == "needs_review"
    assert report["automatically_approved"] is False
    assert report["reasons"]


def test_quality_gate_marks_ocr_requirement_explicitly() -> None:
    report = extraction_quality(
        character_count=0,
        page_count=3,
        segment_count=0,
        status="needs_ocr",
    )
    assert report["outcome"] == "needs_ocr"
    assert report["automatically_approved"] is False


def test_quality_gate_does_not_auto_approve_extracted_text() -> None:
    report = extraction_quality(
        character_count=1200,
        page_count=4,
        segment_count=8,
        status="extracted",
    )
    assert report["outcome"] == "ready_for_review"
    assert report["automatically_approved"] is False
