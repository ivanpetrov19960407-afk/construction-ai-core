import asyncio

from core.rag_engine import RAGEngine


class _Collection:
    def __init__(self) -> None:
        self.last_where = None

    def query(self, *, query_embeddings, n_results, include, where):
        _ = (query_embeddings, n_results, include)
        self.last_where = where
        return {
            "documents": [["chunk text"]],
            "metadatas": [
                [
                    {
                        "source": "doc",
                        "page": 2,
                        "document_id": "d1",
                        "chunk_id": "c1",
                        "jurisdiction": "RU",
                        "authority": "Минстрой",
                        "document_version": "2025",
                        "effective_from": "2025-01-01",
                        "effective_to": None,
                        "is_active": True,
                        "ingested_at": "2026-01-01",
                        "checksum": "x",
                        "text_hash": "y",
                        "source_type": "norm",
                        "quality_score": 0.9,
                        "tenant_id": "t1",
                        "org_id": "o1",
                        "project_id": "p1",
                        "user_id": "u1",
                    }
                ]
            ],
            "distances": [[0.1]],
        }


class _Engine(RAGEngine):
    def __init__(self) -> None:
        self.collection = _Collection()
        self.supports_identity_filters = True

    def _embed_texts(self, texts):
        _ = texts
        return [[0.1, 0.2]]


def test_rag_search_returns_extended_metadata_and_where_contract() -> None:
    engine = _Engine()
    rows = asyncio.run(
        engine.search(
            "q",
            filter_scope="project",
            tenant_id="t1",
            org_id="o1",
            project_id="p1",
            user_id="u1",
        )
    )
    row = rows[0]
    assert row["document_id"] == "d1"
    assert row["chunk_id"] == "c1"
    assert row["jurisdiction"] == "RU"
    assert row["chunk_text"] == "chunk text"
    where = engine.collection.last_where
    assert where and "$and" in where
    assert {"tenant_id": "t1"} in where["$and"]
    assert {"project_id": "p1"} in where["$and"]
