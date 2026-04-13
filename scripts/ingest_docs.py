"""CLI-скрипт для загрузки нормативных документов в ChromaDB."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.rag_engine import RAGEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Индексация PDF/TXT документов в RAGEngine")
    parser.add_argument("--path", required=True, help="Путь к папке с документами")
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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    base_path = Path(args.path)
    if not base_path.exists() or not base_path.is_dir():
        print(f"❌ Папка не найдена: {base_path}")
        return 1

    rag = RAGEngine(collection_name=args.collection)
    files = iter_files(base_path, args.type)
    if not files:
        print("⚠️ Подходящие файлы не найдены")
        return 0

    total_chunks = 0
    processed = 0

    for index, file in enumerate(files, start=1):
        try:
            if file.suffix.lower() == ".pdf":
                chunks = rag.ingest_pdf(str(file), source_name=file.stem)
            else:
                text = file.read_text(encoding="utf-8")
                chunks = rag.ingest_text(text, source_name=file.stem)

            processed += 1
            total_chunks += chunks
            print(f"[{index}/{len(files)}] ✅ {file.name}: добавлено чанков {chunks}")
        except Exception as exc:
            print(f"[{index}/{len(files)}] ❌ {file.name}: ошибка — {exc}")

    print("\nИтоговая статистика:")
    print(f"- Обработано файлов: {processed}/{len(files)}")
    print(f"- Добавлено чанков: {total_chunks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
