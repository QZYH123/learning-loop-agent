import copy

from backend.tests.conftest import make_client
from backend.tests.test_exam_workflow_api import ExamFakeModel, _prepare_editable_draft


def _choice_slot(draft):
    return next(item for item in draft["questions"] if item["planned_type"] == "single-choice")


def _set_option_text(question, option_id, text):
    for option in question["options"]:
        if option["id"] != option_id:
            continue
        content = option["content"]
        if isinstance(content, list) and content and isinstance(content[0], dict):
            option["content"] = [{**content[0], "type": "markdown", "text": text}]
        else:
            option["content"] = text
        return
    raise AssertionError(f"missing option {option_id}")


def _put_choice(client, draft, mutate):
    slot = _choice_slot(draft)
    question = copy.deepcopy(slot["question"])
    mutate(question)
    response = client.put(f"/api/exam-drafts/{draft['id']}/questions/{slot['id']}", json=question)
    assert response.status_code == 200, response.text
    refreshed = client.get(f"/api/exam-drafts/{draft['id']}").json()
    return next(item for item in refreshed["questions"] if item["id"] == slot["id"])


def test_none_of_the_above_option_is_needs_review(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        _, draft = _prepare_editable_draft(client)
        slot = _put_choice(client, draft, lambda question: _set_option_text(question, "B", "以上都不对"))
        assert slot["status"] == "needs-review"
        assert slot["question"]["reliability"] == "needs-review"
        assert slot["question"]["evidence"]["status"] == "complete"


def test_answer_leaked_in_stem_is_needs_review(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        _, draft = _prepare_editable_draft(client)
        slot = _choice_slot(draft)
        answer_text = slot["question"]["options"][0]["content"][0]["text"]

        def leak(question):
            question["stem"] = [{**question["stem"][0], "text": f"The answer is {answer_text}, right?"}]

        updated = _put_choice(client, draft, leak)
        assert updated["status"] == "needs-review"
        assert updated["question"]["reliability"] == "needs-review"


def test_duplicate_options_are_needs_review(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        _, draft = _prepare_editable_draft(client)
        slot = _choice_slot(draft)
        first = slot["question"]["options"][0]["content"][0]["text"]
        updated = _put_choice(client, draft, lambda question: _set_option_text(question, "B", first))
        assert updated["status"] == "needs-review"


def test_ordinary_choice_stays_reliable(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        _, draft = _prepare_editable_draft(client)
        slot = _choice_slot(draft)
        assert slot["status"] == "complete"
        assert slot["question"]["reliability"] == "reliable"
