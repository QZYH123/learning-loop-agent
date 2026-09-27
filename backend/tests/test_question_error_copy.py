import json

from backend.app.exams import ExamService


def test_structure_error_message_hides_internal_fields():
    assert "填空" in ExamService._structure_error_message(ValueError("'blanks'"))
    assert "得分点" in ExamService._structure_error_message(KeyError("scoring_points"))
    assert "正文" in ExamService._structure_error_message(ValueError("content blocks must be a string or list"))
    assert "结构不完整" in ExamService._structure_error_message(TypeError("x"))
    assert "无法解析" in ExamService._structure_error_message(json.JSONDecodeError("Expecting value", "", 0))
    assert "Expecting" not in ExamService._structure_error_message(json.JSONDecodeError("Expecting value", "", 0))


def test_choice_ids_do_not_use_the_first_letter_of_a_sentence():
    extract = ExamService._extract_choice_ids
    options = ["A", "B", "C", "D"]
    assert extract(ExamService, "Because the second instruction stalls", options) == ["Because the second instruction stalls"]
    assert extract(ExamService, "B", options) == ["B"]
    assert extract(ExamService, "C.", options) == ["C"]
    assert extract(ExamService, 1, options) == ["A"]
    assert extract(ExamService, 2, options) == ["B"]
