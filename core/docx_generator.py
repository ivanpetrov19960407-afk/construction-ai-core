"""Утилита генерации DOCX из Jinja2-шаблонов."""

from __future__ import annotations

import subprocess
import sys
from io import BytesIO
from pathlib import Path

from docxtpl import DocxTemplate


class DocxGenerator:
    """Генератор DOCX на базе docxtpl."""

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.templates_dir = Path(templates_dir) if templates_dir else self.base_dir / "templates"
        self.generate_script = self.base_dir / "scripts" / "generate_templates.py"

    def _run_template_generator(self) -> None:
        if not self.generate_script.exists():
            raise FileNotFoundError(f"Template generator script not found: {self.generate_script}")

        subprocess.run(
            [sys.executable, str(self.generate_script), str(self.templates_dir)],
            cwd=str(self.base_dir),
            check=True,
        )

    def _ensure_template(self, template_name: str) -> Path:
        template_path = self.templates_dir / f"{template_name}.docx"
        if template_path.exists():
            return template_path

        self._run_template_generator()

        if template_path.exists():
            return template_path

        raise FileNotFoundError(f"Template not found: {template_path}")

    def generate(self, template_name: str, context: dict) -> bytes:
        """Сгенерировать DOCX по шаблону и вернуть bytes."""
        template_path = self._ensure_template(template_name)

        tpl = DocxTemplate(str(template_path))
        tpl.render(context)

        buffer = BytesIO()
        tpl.save(buffer)
        return buffer.getvalue()

    def _collect_templates(self) -> list[str]:
        return sorted(
            path.stem
            for path in self.templates_dir.glob("*.docx")
            if path.is_file()
        )

    def list_templates(self) -> list[str]:
        """Реальный список доступных DOCX-шаблонов (без расширения)."""
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        templates = self._collect_templates()

        if not templates:
            self._run_template_generator()
            templates = self._collect_templates()

        return templates
