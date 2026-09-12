"""Unified exam render documents and durable export copies."""
from __future__ import annotations

import asyncio
import copy
import html
import io
import os
import time
import uuid
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image as PdfImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .files import write_bytes_atomic
from .learning import LearningError
from .operations import OperationFailure


class ExamRenderingService:
    def __init__(self, exams, data_dir: str | os.PathLike, now=None, id_factory=None):
        self.exams = exams
        self.learning = exams.learning
        self.operations = exams.operations
        self.sources = exams.sources
        self.exports_dir = Path(data_dir) / "exports"
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")
        self._recover_interrupted_exports()

    def get_render_document(self, exam_id: str, edition: str) -> dict:
        subject, exam = self.learning._find_owned("exams", exam_id)
        return self._render_document(subject, exam, exam["current_version_id"], edition)

    def create_export(self, exam_id: str, payload: dict) -> dict:
        subject, exam = self.learning._find_owned("exams", exam_id)
        version_id = exam["current_version_id"]
        attempt_id = payload.get("attempt_id")
        if attempt_id:
            attempt_subject, attempt = self.learning._find_owned("attempts", attempt_id)
            if attempt_subject["id"] != subject["id"] or attempt["exam_id"] != exam_id:
                raise LearningError(422, "VALIDATION_FAILED", "作答记录不属于该试卷")
            if payload["edition"] == "solutions" and attempt["mode"] == "exam" and attempt.get("completion_status") != "completed":
                raise LearningError(409, "EXPORT_ANSWER_NOT_ALLOWED", "考试模式提交前不能导出答案版")
            version_id = attempt["exam_version_id"]

        export_id = self._ids("export")
        timestamp = self._now()
        extension = "pdf" if payload["format"] == "pdf" else "md"
        mime_type = "application/pdf" if payload["format"] == "pdf" else "text/markdown"
        file_name = f"exam-{exam_id[-8:]}-{payload['edition']}.{extension}"
        export = {
            "id": export_id,
            "exam_id": exam_id,
            "exam_version_id": version_id,
            "format": payload["format"],
            "edition": payload["edition"],
            "status": "queued",
            "file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": None,
            "download_url": None,
            "failure": None,
            "storage_name": f"{export_id}.{extension}",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._append_export(subject["id"], export)
        resource = {"type": "export", "id": export_id}

        async def worker():
            self._replace_export(subject["id"], export_id, {**export, "status": "rendering", "updated_at": self._now()})
            await asyncio.sleep(0)
            try:
                current_subject, current_exam = self.learning._find_owned("exams", exam_id)
                render_started_at = self._now()
                render_started = time.perf_counter()
                render_document = self._render_document(current_subject, current_exam, version_id, payload["edition"])
                if payload["format"] == "pdf":
                    content = await asyncio.to_thread(self._render_pdf, render_document)
                else:
                    markdown = await asyncio.to_thread(self._render_markdown, render_document)
                    content = markdown.encode("utf-8")
                self.operations.record_stage(
                    "render",
                    started_at=render_started_at,
                    completed_at=self._now(),
                    outer_elapsed_ms=max(0, round((time.perf_counter() - render_started) * 1000)),
                )
                export_started_at = self._now()
                export_started = time.perf_counter()
                self._write_atomic(self.exports_dir / export["storage_name"], content)
                self.operations.record_stage(
                    "export",
                    started_at=export_started_at,
                    completed_at=self._now(),
                    outer_elapsed_ms=max(0, round((time.perf_counter() - export_started) * 1000)),
                )
                ready = {
                    **export,
                    "status": "ready",
                    "size_bytes": len(content),
                    "download_url": f"/api/exports/{export_id}/file",
                    "updated_at": self._now(),
                }
                self._replace_export(subject["id"], export_id, ready)
                return resource
            except asyncio.CancelledError:
                self._mark_failed(subject["id"], export, "导出已取消")
                raise
            except Exception as exc:
                self._mark_failed(subject["id"], export, "无法生成导出文件")
                code = getattr(exc, "code", "INTERNAL_ERROR")
                raise OperationFailure(code, "无法生成导出文件", retryable=isinstance(exc, OSError)) from exc

        operation = self.operations.start("exam-export", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    def get_export(self, export_id: str) -> dict:
        _, export = self.learning._find_owned("exam_exports", export_id)
        return self._export_view(export)

    def get_export_file(self, export_id: str) -> tuple[bytes, str, str]:
        _, export = self.learning._find_owned("exam_exports", export_id)
        if export["status"] != "ready":
            raise LearningError(409, "EXPORT_NOT_READY", "导出文件尚未就绪")
        path = self.exports_dir / export["storage_name"]
        if not path.exists():
            raise LearningError(409, "EXPORT_NOT_READY", "导出文件不存在，请重新导出")
        return path.read_bytes(), export["mime_type"], export["file_name"]

    def _render_document(self, subject: dict, exam: dict, version_id: str, edition: str) -> dict:
        document = self.exams._version_document(subject, exam["id"], version_id)
        questions = []
        for ordinal, item in enumerate(document["questions"], start=1):
            question = {
                "id": item["id"],
                "ordinal": ordinal,
                "type": item["type"],
                "stem": copy.deepcopy(item["stem"]),
                "options": copy.deepcopy(item.get("options", [])),
                "score": item["score"],
                "answer_area": copy.deepcopy(item["answer_area"]),
            }
            solution = None
            if edition == "solutions":
                solution = {
                    "answer": copy.deepcopy(item["answer"]),
                    "explanation": copy.deepcopy(item["explanation"]),
                    "knowledge_points": list(item["knowledge_points"]),
                    "evidence": copy.deepcopy(item["evidence"]),
                    "reliability": item["reliability"],
                }
            questions.append({"question": question, "solution": solution})
        return {
            "exam_id": exam["id"],
            "exam_version_id": version_id,
            "edition": edition,
            "title": document["title"],
            "instructions": copy.deepcopy(document["instructions"]),
            "questions": questions,
            "total_score": sum(item["question"]["score"] for item in questions),
            "layout": {
                "paper_size": "A4",
                "margins_mm": {"top": 18, "right": 16, "bottom": 18, "left": 16},
            },
        }

    def _render_markdown(self, document: dict) -> str:
        lines = [f"# {document['title']}", "", f"总分：{document['total_score']:g}", ""]
        for block in document["instructions"]:
            lines.extend([self._block_markdown(block), ""])
        for item in document["questions"]:
            question = item["question"]
            lines.extend([f"## {question['ordinal']}.（{question['score']:g} 分）", ""])
            for block in question["stem"]:
                lines.extend([self._block_markdown(block), ""])
            for option in question.get("options", []):
                content = " ".join(self._block_markdown(block) for block in option["content"])
                lines.append(f"- {option['id']}. {content}")
            if question.get("options"):
                lines.append("")
            for _ in range(question["answer_area"]["lines"]):
                lines.extend(["________________________________________", ""])
            if item["solution"] is not None:
                solution = item["solution"]
                lines.extend(["### 答案与解析", "", f"**答案：** {self._answer_text(solution['answer'])}", ""])
                for block in solution["explanation"]:
                    lines.extend([self._block_markdown(block), ""])
                if solution["knowledge_points"]:
                    lines.extend([f"**考点：** {'、'.join(solution['knowledge_points'])}", ""])
                citations = solution["evidence"].get("citations", [])
                if citations:
                    sources = "；".join(f"{item['source_name']}（{item['location']['label']}）" for item in citations)
                    lines.extend([f"**依据：** {sources}", ""])
        return "\n".join(lines).rstrip() + "\n"

    def _render_pdf(self, document: dict) -> bytes:
        if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font = "STSong-Light"
        body = ParagraphStyle("ExamBody", fontName=font, fontSize=10.5, leading=16, spaceAfter=5)
        title = ParagraphStyle("ExamTitle", parent=body, fontSize=20, leading=26, alignment=TA_CENTER, spaceAfter=12)
        heading = ParagraphStyle("ExamHeading", parent=body, fontSize=12, leading=18, spaceBefore=5, spaceAfter=5)
        muted = ParagraphStyle("ExamMuted", parent=body, fontSize=9, textColor=colors.HexColor("#555555"))
        margins = document["layout"]["margins_mm"]
        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4 if document["layout"]["paper_size"] == "A4" else LETTER,
            topMargin=margins["top"] * mm,
            rightMargin=margins["right"] * mm,
            bottomMargin=margins["bottom"] * mm,
            leftMargin=margins["left"] * mm,
            title=document["title"],
        )
        story = [Paragraph(html.escape(document["title"]), title), Paragraph(f"总分：{document['total_score']:g}", muted)]
        story.extend(self._pdf_blocks(document["instructions"], body))
        for item in document["questions"]:
            question = item["question"]
            prompt_section = [Paragraph(f"{question['ordinal']}.（{question['score']:g} 分）", heading)]
            prompt_section.extend(self._pdf_blocks(question["stem"], body))
            for option in question.get("options", []):
                option_text = " ".join(self._plain_block(block) for block in option["content"])
                prompt_section.append(Paragraph(f"{html.escape(option['id'])}. {html.escape(option_text)}", body))
            # 题干可能跨页；让 ReportLab 自然分页，避免超长题目触发 LayoutError。
            story.extend(prompt_section)
            for _ in range(question["answer_area"]["lines"]):
                story.extend([Spacer(1, 4), Paragraph("_" * 70, muted)])
            if item["solution"] is not None:
                solution = item["solution"]
                solution_section = [
                    Paragraph("答案与解析", heading),
                    Paragraph(f"答案：{html.escape(self._answer_text(solution['answer']))}", body),
                    *self._pdf_blocks(solution["explanation"], body),
                ]
                if solution["knowledge_points"]:
                    solution_section.append(Paragraph(f"考点：{html.escape('、'.join(solution['knowledge_points']))}", muted))
                story.extend(solution_section)
            story.append(Spacer(1, 8))
        pdf.build(story, onFirstPage=self._draw_page_number, onLaterPages=self._draw_page_number)
        return buffer.getvalue()

    def _pdf_blocks(self, blocks: list[dict], style: ParagraphStyle) -> list:
        flowables = []
        for block in blocks:
            if block["type"] == "table":
                data = [[Paragraph(html.escape(str(cell)), style) for cell in block["columns"]]]
                data.extend([[Paragraph(html.escape(str(cell)), style) for cell in row] for row in block["rows"]])
                table = Table(data, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#777777")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]))
                flowables.extend([table, Spacer(1, 5)])
            elif block["type"] == "image":
                content, _ = self.sources.get_asset(block["asset"]["source_version_id"], block["asset"]["asset_id"])
                image = PdfImage(io.BytesIO(content))
                scale = min(160 * mm / image.imageWidth, 90 * mm / image.imageHeight, 1)
                image.drawWidth = image.imageWidth * scale
                image.drawHeight = image.imageHeight * scale
                flowables.extend([image, Spacer(1, 4)])
                if block.get("caption") or block.get("alt"):
                    flowables.append(Paragraph(html.escape(block.get("caption") or block.get("alt")), style))
            else:
                text = self._plain_block(block)
                flowables.append(Paragraph(html.escape(text).replace("\n", "<br/>"), style))
        return flowables

    @staticmethod
    def _draw_page_number(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("STSong-Light", 8)
        canvas.drawCentredString(document.pagesize[0] / 2, 9 * mm, str(document.page))
        canvas.restoreState()

    @staticmethod
    def _answer_text(answer: dict) -> str:
        if answer["kind"] == "choice":
            return "、".join(answer["option_ids"])
        if answer["kind"] == "true-false":
            return "正确" if answer["value"] else "错误"
        if answer["kind"] == "fill-blank":
            return "；".join("/".join(item["acceptable_answers"]) for item in answer["blanks"])
        return " ".join(ExamRenderingService._plain_block(block) for block in answer["reference_answer"])

    @staticmethod
    def _plain_block(block: dict) -> str:
        if block["type"] == "markdown":
            return block["text"]
        if block["type"] == "latex":
            return block["latex"]
        if block["type"] == "table":
            return " | ".join(block["columns"])
        return block.get("caption") or block.get("alt") or "图片"

    @staticmethod
    def _block_markdown(block: dict) -> str:
        if block["type"] == "markdown":
            return block["text"]
        if block["type"] == "latex":
            marker = "$$" if block["display"] else "$"
            return f"{marker}{block['latex']}{marker}"
        if block["type"] == "table":
            header = "| " + " | ".join(block["columns"]) + " |"
            divider = "| " + " | ".join("---" for _ in block["columns"]) + " |"
            rows = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in block["rows"]]
            return "\n".join([header, divider, *rows])
        asset = block["asset"]
        alt = block.get("alt") or block.get("caption") or "图片"
        return f"![{alt}](/api/source-versions/{asset['source_version_id']}/assets/{asset['asset_id']})"

    def _append_export(self, subject_id: str, export: dict) -> None:
        self.learning._mutate(subject_id, lambda data: {
            **data,
            "exam_exports": [*data.get("exam_exports", []), export],
        })

    def _replace_export(self, subject_id: str, export_id: str, export: dict) -> None:
        self.learning._mutate(subject_id, lambda data: {
            **data,
            "exam_exports": [export if item["id"] == export_id else item for item in data.get("exam_exports", [])],
        })

    def _mark_failed(self, subject_id: str, export: dict, message: str) -> None:
        failed = {
            **export,
            "status": "failed",
            "failure": {"code": "INTERNAL_ERROR", "message": message, "retryable": True, "details": {}},
            "updated_at": self._now(),
        }
        self._replace_export(subject_id, export["id"], failed)

    def _recover_interrupted_exports(self) -> None:
        timestamp = self._now()
        for subject in self.learning.workspace_service.snapshot().get("subjects", []):
            if not any(item.get("status") in {"queued", "rendering"} for item in subject.get("data", {}).get("exam_exports", [])):
                continue
            self.learning._mutate(subject["id"], lambda data: {
                **data,
                "exam_exports": [
                    {
                        **item,
                        "status": "failed",
                        "failure": {
                            "code": "INTERNAL_ERROR",
                            "message": "服务重启中断了导出，请重新创建导出副本",
                            "retryable": True,
                            "details": {},
                        },
                        "updated_at": timestamp,
                    }
                    if item.get("status") in {"queued", "rendering"} else item
                    for item in data.get("exam_exports", [])
                ],
            })

    @staticmethod
    def _export_view(export: dict) -> dict:
        return {
            key: export.get(key)
            for key in (
                "id",
                "exam_id",
                "exam_version_id",
                "format",
                "edition",
                "status",
                "file_name",
                "mime_type",
                "size_bytes",
                "download_url",
                "failure",
                "created_at",
                "updated_at",
            )
        }

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        write_bytes_atomic(path, content)
