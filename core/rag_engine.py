"""RAG движок для поиска релевантных строительных нормативов."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import chromadb
import pdfplumber

from config.settings import settings

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - fallback when dependency is unavailable
    SentenceTransformer = None


class RAGEngine:
    """RAG-движок для индексации и поиска фрагментов нормативной документации."""

    def __init__(self, collection_name: str = "construction_norms"):
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self.embedding_model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        self.embedding_model = self._load_embedding_model()
        self.collection = self.client.get_or_create_collection(name=collection_name)

    async def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Найти релевантные чанки в ChromaDB."""
        query_embedding = self._embed_texts([query])[0]
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas"],
        )

        documents = result.get("documents", [[]])
        metadatas = result.get("metadatas", [[]])

        rows: list[dict] = []
        for text, meta in zip(documents[0], metadatas[0], strict=False):
            metadata = meta or {}
            rows.append(
                {
                    "text": text,
                    "source": str(metadata.get("source", "unknown")),
                    "page": int(metadata.get("page", 0)),
                }
            )
        return rows

    def ingest_pdf(self, filepath: str, source_name: str) -> int:
        """Извлечь текст из PDF, разбить на чанки и добавить в индекс."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {filepath}")

        added = 0
        with pdfplumber.open(path) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                chunks = self._chunk_text(text)
                added += self._upsert_chunks(chunks, source_name, page=page_index)
        return added

    def ingest_text(self, text: str, source_name: str, metadata: dict | None = None) -> int:
        """Добавить текстовые данные напрямую в индекс."""
        chunks = self._chunk_text(text)
        if not chunks:
            return 0

        payload = dict(metadata or {})
        return self._upsert_chunks(
            chunks,
            source_name,
            page=int(payload.pop("page", 0)),
            extra=payload,
        )

    def _load_embedding_model(self):
        if SentenceTransformer is None:
            return None
        try:
            return SentenceTransformer(self.embedding_model_name)
        except Exception:
            return None

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.embedding_model is not None:
            vectors = self.embedding_model.encode(texts, normalize_embeddings=True)
            return vectors.tolist()

        vectors: list[list[float]] = []
        dimension = 384
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = [0.0] * dimension
            for idx in range(dimension):
                values[idx] = digest[idx % len(digest)] / 255.0
            vectors.append(values)
        return vectors

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
        tokens = text.split()
        if not tokens:
            return []

        chunks: list[str] = []
        step = chunk_size - overlap
        for start in range(0, len(tokens), step):
            chunk_tokens = tokens[start : start + chunk_size]
            if not chunk_tokens:
                continue
            chunks.append(" ".join(chunk_tokens))
            if start + chunk_size >= len(tokens):
                break
        return chunks

    def _upsert_chunks(
        self,
        chunks: list[str],
        source_name: str,
        *,
        page: int,
        extra: dict[str, Any] | None = None,
    ) -> int:
        if not chunks:
            return 0

        extra_meta = extra or {}
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{"source": source_name, "page": page, **extra_meta} for _ in chunks]
        embeddings = self._embed_texts(chunks)

        self.collection.add(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
        return len(chunks)
