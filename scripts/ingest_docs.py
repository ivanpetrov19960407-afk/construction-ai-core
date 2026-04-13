"""CLI-скрипт для загрузки нормативных документов в ChromaDB."""

from __future__ import annotations

import argparse
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


def _load_catalog(rag: RAGEngine, base_path: Path | None) -> tuple[int, int]:
    total_chunks = 0
    processed = 0
    pdf_files = sorted(base_path.glob("*.pdf")) if base_path else []

    for norm in tqdm(NORMS_CATALOG, desc="Каталог", unit="norm"):
        code = norm["code"]
        title = norm["title"]
        metadata = {"tags": norm.get("tags", []), "scope": norm.get("scope", [])}
        pdf_match = next(
            (
                f
                for f in pdf_files
                if code.lower() in f.stem.lower()
                or title.lower() in f.stem.lower()
            ),
            None,
        )

        if pdf_match:
            chunks = rag.ingest_pdf(str(pdf_match), source_name=code, metadata=metadata)
        else:
            placeholder = f"{title}. Краткое описание: документ из каталога нормативов для стройки."
            chunks = rag.ingest_text(placeholder, source_name=code, metadata=metadata)

        processed += 1
        total_chunks += chunks
    return processed, total_chunks


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    base_path: Path | None = None
    if args.path:
        base_path = Path(args.path)
        if not base_path.exists() or not base_path.is_dir():
            print(f"❌ Папка не найдена: {base_path}")
            return 1

    if not args.path and not args.catalog:
        print("❌ Укажите --path или включите --catalog")
        return 1

    rag = RAGEngine(collection_name=args.collection)
    if args.clear:
        rag.clear_collection()
        print("🧹 Коллекция очищена")

    total_chunks = 0
    processed = 0

    if args.catalog:
        loaded, chunks = _load_catalog(rag, base_path)
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

    print("\nИтоговая статистика:")
    print(f"- Обработано источников: {processed}")
    print(f"- Добавлено чанков: {total_chunks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
