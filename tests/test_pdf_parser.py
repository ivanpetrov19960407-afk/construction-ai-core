"""Tests for PDFParser."""

from core.pdf_parser import PDFParser


def test_extract_normative_refs():
    """Parser should extract and normalize normative references."""
    parser = PDFParser()

    text = "согласно СП 48.13330.2019 и ГОСТ Р 21.1101"
    result = parser.extract_normative_refs(text)

    assert result == ["СП 48.13330", "ГОСТ Р 21.1101"]


def test_parse_pdf_extracts_text_and_metadata():
    """Parser should read PDF pages and produce chunks."""
    parser = PDFParser()
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\n"
        b"endobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"5 0 obj\n<< /Length 58 >>\nstream\n"
        b"BT /F1 12 Tf 72 720 Td (SP 48.13330.2019 test text) Tj ET\n"
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

    result = parser.parse(file_bytes=pdf_bytes, filename="sample.pdf")

    assert result.filename == "sample.pdf"
    assert result.total_pages == 1
    assert result.text_chunks
    assert any("SP 48.13330.2019" in chunk for chunk in result.text_chunks)
    assert isinstance(result.tables, list)
    assert isinstance(result.metadata, dict)
