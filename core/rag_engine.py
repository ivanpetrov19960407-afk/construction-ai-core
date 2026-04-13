"""RAG движок для поиска релевантных строительных нормативов."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import chromadb
import pdfplumber

from config.settings import settings

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - fallback when dependency is unavailable
    SentenceTransformer = None  # type: ignore[misc,assignment]


class RAGEngine:
    """RAG-движок для индексации и поиска фрагментов нормативной документации."""

    def __init__(self, collection_name: str = "construction_norms"):
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self.embedding_model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        self.embedding_model: Any | None = None
        self.embedding_backend = os.getenv("RAG_EMBEDDINGS_BACKEND", "sentence_transformers")
        self.collection = self.client.get_or_create_collection(name=collection_name)

    async def search(
        self,
        query: str,
        n_results: int = 5,
        filter_scope: str | None = None,
    ) -> list[dict]:
        """Найти релевантные чанки в ChromaDB."""
        query_embedding = self._embed_texts([query])[0]
        where: dict[str, Any] | None = None
        if filter_scope:
            where = {"scope": {"$contains": filter_scope}}

        result = cast(Any, self.collection).query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas"],
            where=where,
        )

        documents = cast(list[list[str]], result.get("documents") or [[]])
        metadatas = cast(list[list[dict[str, Any]]], result.get("metadatas") or [[]])

        rows: list[dict] = []
        for text, meta in zip(documents[0], metadatas[0], strict=False):
            metadata = meta or {}
            rows.append(
                {
                    "text": text,
                    "source": str(metadata.get("source", "unknown")),
                    "page": int(metadata.get("page", 0)),
                    "tags": list(metadata.get("tags", [])),
                    "scope": list(metadata.get("scope", [])),
                }
            )
        return rows

    def ingest_pdf(self, filepath: str, source_name: str, metadata: dict | None = None) -> int:
        """Извлечь текст из PDF, разбить на чанки и добавить в индекс."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {filepath}")

        extra = dict(metadata or {})
        added = 0
        with pdfplumber.open(path) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                chunks = self._chunk_text(text)
                added += self._upsert_chunks(chunks, source_name, page=page_index, extra=extra)
        return added

    def ingest_text(self, text: str, source_name: str, metadata: dict | None = None) -> int:
        """Добавить текстовые данные напрямую в индекс."""
        chunks = self._chunk_text(text)
        if not chunks:
            return 0

        payload = dict(metadata or {})
        payload.setdefault("tags", [])
        payload.setdefault("scope", [])
        return self._upsert_chunks(
            chunks,
            source_name,
            page=int(payload.pop("page", 0)),
            extra=payload,
        )

    def clear_collection(self) -> None:
        """Полностью очистить текущую коллекцию ChromaDB."""
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def get_stats(self) -> dict[str, Any]:
        """Вернуть базовую статистику по коллекции."""
        total_chunks = int(self.collection.count())
        payload = cast(Any, self.collection).get(include=["metadatas"])
        metadatas = cast(list[dict[str, Any]], payload.get("metadatas") or [])

        sources = sorted({str(meta.get("source")) for meta in metadatas if meta.get("source")})
        timestamps = [str(meta.get("ingested_at")) for meta in metadatas if meta.get("ingested_at")]
        last_updated = max(timestamps) if timestamps else ""

        return {
            "total_chunks": total_chunks,
            "sources": sources,
            "last_updated": last_updated,
        }

    def _get_embedding_model(self) -> Any | None:
        if self.embedding_backend != "sentence_transformers":
            return None

        if self.embedding_model is not None:
            return self.embedding_model

        if SentenceTransformer is None:
            self.embedding_backend = "hash"
            return None

        try:
            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            return self.embedding_model
        except Exception:
            self.embedding_backend = "hash"
            return None

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        embedding_model = self._get_embedding_model()
        if embedding_model is not None:
            model_vectors = embedding_model.encode(texts, normalize_embeddings=True)
            return cast(list[list[float]], model_vectors.tolist())

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

        extra_meta = dict(extra or {})
        extra_meta.setdefault("tags", [])
        extra_meta.setdefault("scope", [])
        extra_meta["ingested_at"] = datetime.now(timezone(timedelta())).isoformat()

        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{"source": source_name, "page": page, **extra_meta} for _ in chunks]
        embeddings = self._embed_texts(chunks)

        self.collection.add(
            ids=ids,
            documents=chunks,
            metadatas=cast(Any, metadatas),
            embeddings=cast(Any, embeddings),
        )
        return len(chunks)
