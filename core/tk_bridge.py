"""Bridge для интеграции с внешним tk-generator (Node.js)."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from config.settings import settings


class TKGeneratorBridge:
    """Вызывает внешний tk-generator и возвращает пути к артефактам."""

    def __init__(self, tk_generator_path: str = settings.tk_generator_path):
        self.path = tk_generator_path

    async def generate(self, input_json: dict[str, Any]) -> dict[str, str]:
        """Вызывает tk-generator через subprocess и возвращает результат."""
        generator_root = Path(self.path).expanduser().resolve()
        out_dir = Path(tempfile.mkdtemp(prefix="tk_generator_out_"))
        timeout_seconds = 120

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as input_file:
            json.dump(input_json, input_file, ensure_ascii=False, indent=2)
            input_path = Path(input_file.name)

        try:
            cmd = [
                "node",
                "src/index.js",
                "--input",
                str(input_path),
                "--output",
                str(out_dir),
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(generator_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )
            except TimeoutError as exc:
                process.kill()
                await process.wait()
                raise RuntimeError(
                    f"tk-generator timed out after {timeout_seconds} seconds"
                ) from exc

            if process.returncode != 0:
                raise RuntimeError(
                    "tk-generator failed: "
                    f"returncode={process.returncode}, stdout={stdout.decode(errors='ignore')}, "
                    f"stderr={stderr.decode(errors='ignore')}"
                )

            docx_file = next(out_dir.rglob("*.docx"), None)
            pdf_file = next(out_dir.rglob("*.pdf"), None)

            return {
                "output_dir": str(out_dir),
                "docx_path": str(docx_file) if docx_file else "",
                "pdf_path": str(pdf_file) if pdf_file else "",
            }
        finally:
            input_path.unlink(missing_ok=True)

    def is_available(self) -> bool:
        """Проверяет что tk-generator установлен и Node.js доступен."""
        generator_root = Path(self.path).expanduser().resolve()
        index_file = generator_root / "src" / "index.js"
        node_binary = shutil.which("node")
        return bool(node_binary and generator_root.exists() and index_file.exists())
