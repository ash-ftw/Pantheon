from __future__ import annotations

import re
from textwrap import wrap
from typing import Any

from app.models import Report


def build_report_pdf(report: Report) -> bytes:
    """Build a small dependency-free PDF for academic report export."""
    lines = _report_lines(report)
    pages = [lines[index : index + 42] for index in range(0, len(lines), 42)] or [["Pantheon report"]]
    objects: list[bytes] = []

    def add_object(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    catalog_id = add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_refs_placeholder = b""
    pages_id = add_object(page_refs_placeholder)
    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []

    for page_lines in pages:
        content = _content_stream(page_lines)
        content_id = add_object(
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
        )
        page_id = add_object(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>"
    ).encode("ascii")
    return _serialize_pdf(objects, catalog_id)


def _report_lines(report: Report) -> list[str]:
    body: dict[str, Any] = report.report_json or {}
    lab = body.get("labInformation") or {}
    scenario = body.get("attackScenario") or {}
    ai = body.get("aiClassification") or {}
    comparison = body.get("beforeAfterComparison") or {}
    recommendations = body.get("defenseRecommendations") or []
    targets = body.get("targetApplications") or []

    raw_lines = [
        "Pantheon Simulation Report",
        report.title,
        "",
        f"Summary: {report.summary}",
        f"Generated: {report.created_at.isoformat()}",
        "",
        "Lab Information",
        f"Lab: {lab.get('labName', 'Unknown')}",
        f"Namespace: {lab.get('namespace', 'Unknown')}",
        f"Template: {body.get('organizationTemplate', 'Unknown')}",
        f"Status: {lab.get('status', 'Unknown')}",
        "",
        "Attack Scenario",
        f"Name: {scenario.get('name', 'Unknown')}",
        f"Type: {scenario.get('attackType', 'Unknown')}",
        f"Difficulty: {scenario.get('difficulty', 'Unknown')}",
        f"Risk: {body.get('riskLevel', 'Unknown')}",
        "",
        "AI Classification",
        f"Classification: {ai.get('classification', 'Unknown')}",
        f"Confidence: {round(float(ai.get('confidenceScore') or 0) * 100)}%",
        f"Explanation: {ai.get('explanation', 'Not available')}",
        "",
        "Target Applications",
        *[
            f"- {target.get('appName')} ({target.get('serviceName')}): {target.get('status')} {target.get('internalUrl')}"
            for target in targets
        ],
        "",
        "Defense Recommendations",
        *[
            f"- {item.get('title')} [{item.get('priority')}]: {item.get('description')}"
            for item in recommendations[:8]
        ],
        "",
        "Before / After",
        _comparison_line(comparison),
        "",
        "Conclusion",
        str(body.get("conclusion") or "No conclusion available."),
    ]
    return _wrap_lines(raw_lines)


def _comparison_line(comparison: dict[str, Any]) -> str:
    if not comparison:
        return "No before/after comparison has been generated yet."
    before = comparison.get("before") or {}
    after = comparison.get("after") or {}
    improvement = comparison.get("improvement") or {}
    return (
        f"Before risk {before.get('riskLevel', 'Unknown')} with {before.get('suspiciousEvents', 0)} events; "
        f"after risk {after.get('riskLevel', 'Unknown')} with {after.get('suspiciousEvents', 0)} events; "
        f"depth reduction {improvement.get('attackDepthReducedPercent', 0)}%."
    )


def _wrap_lines(lines: list[str]) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        safe_line = _to_pdf_text(line)
        if not safe_line:
            wrapped.append("")
            continue
        wrapped.extend(wrap(safe_line, width=92, break_long_words=False) or [""])
    return wrapped


def _content_stream(lines: list[str]) -> bytes:
    chunks = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
    for line in lines:
        chunks.append(f"({_escape_pdf_text(line)}) Tj")
        chunks.append("T*")
    chunks.append("ET")
    return "\n".join(chunks).encode("latin-1", errors="replace")


def _serialize_pdf(objects: list[bytes], catalog_id: int) -> bytes:
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, payload in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(payload)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _to_pdf_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u2192", "->")
    text = re.sub(r"[^\x09\x0a\x0d\x20-\x7e]", "", text)
    return text
