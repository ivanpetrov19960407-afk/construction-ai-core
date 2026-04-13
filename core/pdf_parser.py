"""PDF parsing utilities for document analysis endpoints."""

from __future__ import annotations

import re
from io import BytesIO

import pdfplumber
from pydantic import BaseModel


class ParsedDocument(BaseModel):
    """Structured representation of a parsed PDF document."""

    filename: str
    total_pages: int
    text_chunks: list[str]
    tables: list[list[list]]
    metadata: dict


class PDFParser:
    """Extract text, tables and metadata from PDF files."""

    CHUNK_SIZE = 512
    CHUNK_OVERLAP = 64
    NORMATIVE_PATTERN = re.compile(
        r"(СП\s*\d+\.\d+|СНиП\s*\d+-\d+-\d+|ГОСТ\s*Р?\s*\d+(?:\.\d+)?|ФЗ-\d+|ГК\s*РФ\s*ст\.\s*\d+)",
        flags=re.IGNORECASE,
    )

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        """Parse a PDF into text chunks, tables and metadata."""
        text_parts: list[str] = []
        tables: list[list[list]] = []

        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            metadata = dict(pdf.metadata or {})
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(page_text)

                for table in page.extract_tables() or []:
                    tables.append(table)

            all_text = "\n".join(text_parts)
            chunks = self._chunk_text(all_text)

            return ParsedDocument(
                filename=filename,
                total_pages=len(pdf.pages),
                text_chunks=chunks,
                tables=tables,
                metadata=metadata,
            )

    def extract_normative_refs(self, text: str) -> list[str]:
        """Extract normalized normative references from text."""
        refs: list[str] = []
        for match in self.NORMATIVE_PATTERN.finditer(text):
            value = " ".join(match.group(0).split())
            if value.upper().startswith("ГОСТ"):
                value = value.replace("ГОСТ ", "ГОСТ ")
            if value and value not in refs:
                refs.append(value)
        return refs

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks with overlap."""
        if not text:
            return []

        step = self.CHUNK_SIZE - self.CHUNK_OVERLAP
        chunks: list[str] = []
        for start in range(0, len(text), step):
            chunk = text[start : start + self.CHUNK_SIZE]
            if chunk:
                chunks.append(chunk)
            if start + self.CHUNK_SIZE >= len(text):
                break
        return chunks
