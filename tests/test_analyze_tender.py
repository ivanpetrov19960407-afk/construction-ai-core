"""Тесты /api/analyze/tender."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from api.main import app
from api.routes import analyze
from core.pdf_parser import ParsedDocument


PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
    b"3 0 obj\n"
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\n"
    b"endobj\n"
    b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"5 0 obj\n<< /Length 29 >>\nstream\n"
    b"BT /F1 12 Tf 72 720 Td (44-FZ) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n"
    b"0000000010 00000 n \n"
    b"0000000063 00000 n \n"
    b"0000000120 00000 n \n"
    b"0000000246 00000 n \n"
    b"0000000316 00000 n \n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n426\n%%EOF\n"
)


def test_analyze_tender_contains_44fz_reference():
    """POST /api/analyze/tender возвращает ссылки на 44-ФЗ."""
    client = TestClient(app)

    analyze.pdf_parser.parse = lambda file_bytes, filename: ParsedDocument(
        filename=filename,
        total_pages=1,
        text_chunks=["согласно 44-ФЗ ст.42"],
        tables=[],
        metadata={},
    )
    analyze.orchestrator.process = AsyncMock(
        return_value={
            "session_id": "s-44",
            "state": {
                "risks": ["короткий срок подачи"],
                "contradictions": [],
                "legal_review": "Нужна детализация сроков.",
                "confidence": 0.9,
                "verification": {"recommendation": "УЧАСТВОВАТЬ"},
            },
        }
    )

    response = client.post(
        "/api/analyze/tender",
        files={"file": ("tender.pdf", PDF_BYTES, "application/pdf")},
        data={"role": "tender_specialist"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "44-ФЗ" in data["normative_refs"]
    assert data["recommendation"] == "УЧАСТВОВАТЬ"
