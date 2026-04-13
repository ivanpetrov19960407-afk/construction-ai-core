"""CLI-скрипт для загрузки нормативных документов в ChromaDB."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from tqdm import tqdm

from core.rag_engine import RAGEngine
from scripts.norm_catalog import NORMS_CATALOG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Индексация PDF/TXT документов в RAGEngine")
    parser.add_argument("--path", help="Путь к папке с документами")
    parser.add_argument(
        "--type",
        choices=["pdf", "txt", "all"],
        default="all",
        help="Тип файлов для индексации",
    )
    parser.add_argument(
        "--collection",
        default="construction_norms",
        help="Имя ChromaDB коллекции",
    )
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="Загрузить нормативы из каталога NORMS_CATALOG",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить коллекцию перед загрузкой",
    )
    parser.add_argument(
        "--test-search",
        metavar="QUERY",
        help="Выполнить тестовый поиск в RAG после загрузки и вывести top-5",
    )
    return parser


def iter_files(base_path: Path, file_type: str) -> list[Path]:
    patterns = {
        "pdf": ["*.pdf"],
        "txt": ["*.txt"],
        "all": ["*.pdf", "*.txt"],
    }

    files: list[Path] = []
    for pattern in patterns[file_type]:
        files.extend(sorted(base_path.glob(pattern)))
    return files


def _load_catalog(rag: RAGEngine) -> tuple[int, int]:
    total_chunks = 0
    processed = 0

    for norm in tqdm(NORMS_CATALOG, desc="Каталог", unit="norm"):
        code = norm["code"]
        title = norm["title"]
        description = norm.get("description", "")
        metadata = {
            "title": title,
            "tags": norm.get("tags", []),
            "scope": norm.get("scope", []),
        }

        text = f"{title}\n\n{description}".strip()
        chunks = rag.ingest_text(text, source_name=code, metadata=metadata)
        processed += 1
        total_chunks += chunks

    return processed, total_chunks


def _run_test_search(rag: RAGEngine, query: str) -> None:
    results = asyncio.run(rag.search(query=query, n_results=5))
    print(f'\nРезультаты поиска для запроса: "{query}"')
    if not results:
        print("- Ничего не найдено")
        return

    for index, row in enumerate(results, start=1):
        source = row.get("source", "unknown")
        score = row.get("score", 0.0)
        text = str(row.get("text", "")).strip().replace("\n", " ")
        preview = (text[:160] + "...") if len(text) > 160 else text
        print(f"{index}. source={source}, score={score:.4f}")
        print(f"   {preview}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    base_path: Path | None = None
    if args.path:
        base_path = Path(args.path)
        if not base_path.exists() or not base_path.is_dir():
            print(f"❌ Папка не найдена: {base_path}")
            return 1

    if not args.path and not args.catalog and not args.test_search:
        print("❌ Укажите --path, --catalog или --test-search")
        return 1

    rag = RAGEngine(collection_name=args.collection)
    if args.clear:
        rag.clear_collection()
        print("🧹 Коллекция очищена")

    total_chunks = 0
    processed = 0

    if args.catalog:
        loaded, chunks = _load_catalog(rag)
        processed += loaded
        total_chunks += chunks

    if base_path:
        files = iter_files(base_path, args.type)
        if not files and not args.catalog:
            print("⚠️ Подходящие файлы не найдены")
            return 0

        for file in tqdm(files, desc="Файлы", unit="file"):
            try:
                if file.suffix.lower() == ".pdf":
                    chunks = rag.ingest_pdf(str(file), source_name=file.stem)
                else:
                    text = file.read_text(encoding="utf-8")
                    chunks = rag.ingest_text(text, source_name=file.stem)

                processed += 1
                total_chunks += chunks
            except Exception as exc:
                print(f"❌ {file.name}: ошибка — {exc}")

    if args.catalog:
        print(f"Загружено {processed} документов, {total_chunks} chunks")
    else:
        print("\nИтоговая статистика:")
        print(f"- Обработано источников: {processed}")
        print(f"- Добавлено чанков: {total_chunks}")

    if args.test_search:
        _run_test_search(rag, args.test_search)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
