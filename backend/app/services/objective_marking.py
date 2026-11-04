"""Deterministic server-side marking for objective question types."""

from typing import Any


def mark_objective(
    question_type: str,
    answer_key: dict[str, Any] | None,
    response: dict[str, Any],
    max_marks: int,
) -> tuple[float, bool, dict[str, object]] | None:
    """Return an objective mark, correctness and safe feedback; None means manual marking."""
    if answer_key is None:
        return None

    if question_type == "multiple_choice":
        correct = answer_key.get("correct_option_id")
        selected = response.get("selected_option_id")
        is_correct = isinstance(correct, str) and selected == correct
        awarded = float(max_marks if is_correct else 0)
    elif question_type == "multiple_select":
        correct_values = answer_key.get("correct_option_ids")
        selected_values = response.get("selected_option_ids")
        if not isinstance(correct_values, list) or not isinstance(selected_values, list):
            return None
        correct_set = set(correct_values)
        selected_set = set(selected_values)
        is_correct = selected_set == correct_set
        if answer_key.get("partial_credit") is True:
            raw = max(0, len(correct_set & selected_set) - len(selected_set - correct_set))
            awarded = round(max_marks * raw / max(len(correct_set), 1), 2)
        else:
            awarded = float(max_marks if is_correct else 0)
    elif question_type == "true_false":
        correct = answer_key.get("correct_value")
        selected = response.get("value")
        is_correct = isinstance(correct, bool) and selected is correct
        awarded = float(max_marks if is_correct else 0)
    elif question_type == "fill_blank":
        accepted = answer_key.get("accepted_answers")
        value = response.get("value")
        if not isinstance(accepted, list) or not isinstance(value, str):
            return None
        case_sensitive = answer_key.get("case_sensitive") is True
        trim = answer_key.get("trim_whitespace", True)

        def normalize(item: str) -> str:
            result = item.strip() if trim else item
            return result if case_sensitive else result.casefold()

        is_correct = any(
            isinstance(item, str) and normalize(item) == normalize(value) for item in accepted
        )
        awarded = float(max_marks if is_correct else 0)
    elif question_type == "numeric":
        expected = answer_key.get("value")
        tolerance = answer_key.get("tolerance", 0)
        actual = response.get("value")
        expected_unit = answer_key.get("unit")
        actual_unit = response.get("unit")
        if (
            not isinstance(expected, (int, float))
            or isinstance(expected, bool)
            or not isinstance(tolerance, (int, float))
            or isinstance(tolerance, bool)
            or not isinstance(actual, (int, float))
            or isinstance(actual, bool)
        ):
            return None
        unit_matches = expected_unit in (None, "") or actual_unit == expected_unit
        is_correct = abs(float(actual) - float(expected)) <= float(tolerance) and unit_matches
        awarded = float(max_marks if is_correct else 0)
    elif question_type == "matching":
        correct_pairs = answer_key.get("matches")
        selected_pairs = response.get("matches")
        if not isinstance(correct_pairs, list) or not isinstance(selected_pairs, list):
            return None
        expected = {
            item.get("left_id"): item.get("right_id")
            for item in correct_pairs
            if isinstance(item, dict)
        }
        selected = {
            item.get("left_id"): item.get("right_id")
            for item in selected_pairs
            if isinstance(item, dict)
        }
        if not expected:
            return None
        correct_count = sum(selected.get(left) == right for left, right in expected.items())
        is_correct = correct_count == len(expected)
        awarded = round(max_marks * correct_count / len(expected), 2)
    elif question_type == "ordering":
        correct_order = answer_key.get("ordered_ids")
        selected_order = response.get("ordered_ids")
        if not isinstance(correct_order, list) or not isinstance(selected_order, list) or not correct_order:
            return None
        correct_count = sum(
            index < len(selected_order) and selected_order[index] == expected
            for index, expected in enumerate(correct_order)
        )
        is_correct = selected_order == correct_order
        awarded = round(max_marks * correct_count / len(correct_order), 2)
    else:
        return None

    return awarded, is_correct, {"is_correct": is_correct, "awarded_marks": awarded, "max_marks": max_marks}
