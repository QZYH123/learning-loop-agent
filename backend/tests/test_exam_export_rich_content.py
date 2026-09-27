import copy
import io
from pathlib import Path

from pypdf import PdfReader

from backend.tests.conftest import make_client
from backend.tests.support.exam import ExamFakeModel, build_exam, publish_ready_exam
from backend.tests.support.http import upload_source, wait_for_operation
from backend.tests.support.media import image_bytes

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_rich_exam_export_keeps_blocks_and_hides_solutions(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        subject_id, _, _, blueprint_id = build_exam(client)
        exam = publish_ready_exam(client, blueprint_id)
        uploaded = upload_source(client, subject_id, "diagram.png", image_bytes(), "image/png")
        image_version_id = wait_for_operation(client, uploaded.json()["operation"]["id"])["result"]["id"]
        asset_id = client.get(f"/api/source-versions/{image_version_id}").json()["assets"][0]["id"]

        document = copy.deepcopy(exam["document"])
        choice = next(item for item in document["questions"] if item["type"] == "single-choice")
        choice["stem"] = [
            {
                "id": "block-latex",
                "type": "latex",
                "latex": r"\lim_{x \to 0} \frac{\sin x}{x} = 1",
                "display": True,
            },
            {
                "id": "block-table",
                "type": "table",
                "columns": ["x", "f(x)"],
                "rows": [["0", "1"], ["1", "0.84"]],
            },
            {
                "id": "block-image",
                "type": "image",
                "asset": {"source_version_id": image_version_id, "asset_id": asset_id},
                "alt": "导数示意图",
            },
        ]
        replaced = client.put(
            f"/api/exams/{exam['id']}",
            json={"base_version_id": exam["current_version_id"], "document": document},
        )
        assert replaced.status_code == 200, replaced.text
        exam_id = exam["id"]

        questions = client.get(f"/api/exams/{exam_id}/render-document", params={"edition": "questions"}).json()
        solutions = client.get(f"/api/exams/{exam_id}/render-document", params={"edition": "solutions"}).json()
        question_ids = [item["question"]["id"] for item in questions["questions"]]
        assert question_ids == [item["question"]["id"] for item in solutions["questions"]]
        assert all(item["solution"] is None for item in questions["questions"])
        assert all(item["solution"] is not None for item in solutions["questions"])

        rendered_choice = next(item for item in questions["questions"] if item["question"]["id"] == choice["id"])
        stem_types = [block["type"] for block in rendered_choice["question"]["stem"]]
        assert stem_types == ["latex", "table", "image"]
        assert rendered_choice["question"]["stem"][0]["latex"] == r"\lim_{x \to 0} \frac{\sin x}{x} = 1"
        assert rendered_choice["question"]["stem"][1]["columns"] == ["x", "f(x)"]
        assert rendered_choice["question"]["stem"][2]["asset"]["asset_id"] == asset_id

        markdown_questions = client.post(
            f"/api/exams/{exam_id}/exports",
            json={"format": "markdown", "edition": "questions"},
        ).json()
        assert wait_for_operation(client, markdown_questions["operation"]["id"])["status"] == "succeeded"
        questions_md = client.get(f"/api/exports/{markdown_questions['resource']['id']}/file").text
        assert r"\lim_{x \to 0} \frac{\sin x}{x} = 1" in questions_md
        assert "| x | f(x) |" in questions_md
        assert "导数示意图" in questions_md
        assert "答案与解析" not in questions_md

        markdown_solutions = client.post(
            f"/api/exams/{exam_id}/exports",
            json={"format": "markdown", "edition": "solutions"},
        ).json()
        assert wait_for_operation(client, markdown_solutions["operation"]["id"])["status"] == "succeeded"
        solutions_md = client.get(f"/api/exports/{markdown_solutions['resource']['id']}/file").text
        assert "答案与解析" in solutions_md
        assert r"\lim_{x \to 0} \frac{\sin x}{x} = 1" in solutions_md

        pdf_questions = client.post(
            f"/api/exams/{exam_id}/exports",
            json={"format": "pdf", "edition": "questions"},
        ).json()
        assert wait_for_operation(client, pdf_questions["operation"]["id"])["status"] == "succeeded"
        questions_pdf = client.get(f"/api/exports/{pdf_questions['resource']['id']}/file").content
        assert questions_pdf.startswith(b"%PDF")
        questions_text = _pdf_text(questions_pdf)
        assert "sin x" in questions_text or r"\sin" in questions_text or "lim" in questions_text
        assert "f(x)" in questions_text
        assert "答案与解析" not in questions_text

        pdf_solutions = client.post(
            f"/api/exams/{exam_id}/exports",
            json={"format": "pdf", "edition": "solutions"},
        ).json()
        assert wait_for_operation(client, pdf_solutions["operation"]["id"])["status"] == "succeeded"
        solutions_pdf = client.get(f"/api/exports/{pdf_solutions['resource']['id']}/file").content
        assert solutions_pdf.startswith(b"%PDF")
        solutions_text = _pdf_text(solutions_pdf)
        assert "答案与解析" in solutions_text
        assert len(solutions_pdf) >= len(questions_pdf)


def test_print_path_keeps_katex_and_block_renderers():
    exam_js = (FRONTEND / "js/components/exam.js").read_text(encoding="utf-8")
    app_js = (FRONTEND / "js/app.js").read_text(encoding="utf-8")
    util_js = (FRONTEND / "js/util.js").read_text(encoding="utf-8")
    assert "renderBlocks(question.stem)" in exam_js
    assert "block.type === 'latex'" in util_js
    assert "block.type === 'table'" in util_js
    assert "block.type === 'image'" in util_js
    assert "/vendor/katex/katex.min.css" in app_js
    assert "renderExamPrintDocument(doc)" in app_js


def test_citation_line_drops_repeated_locations_and_keeps_three():
    from backend.app.rendering import ExamRenderingService

    citations = [
        {"source_id": "s1", "source_name": "notes.md", "anchor_id": "a", "location": {"label": "流水线"}},
        {"source_id": "s2", "source_name": "notes.md", "anchor_id": "b", "location": {"label": "章/流水线"}},
        {"source_id": "s", "source_name": "notes.md", "anchor_id": "c", "location": {"label": "冯诺依曼"}},
        {"source_id": "t", "source_name": "cache.txt", "anchor_id": "d", "location": {"label": "段落 1"}},
        {"source_id": "u", "source_name": "extra.md", "anchor_id": "e", "location": {"label": "补充"}},
    ]
    line = ExamRenderingService.citation_line(citations)
    assert line == "notes.md（流水线）；notes.md（冯诺依曼）；cache.txt（段落 1）"
    assert "补充" not in line
