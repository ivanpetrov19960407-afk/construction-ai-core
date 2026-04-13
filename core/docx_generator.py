"""Утилита генерации DOCX из Jinja2-шаблонов."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate


class DocxGenerator:
    """Генератор DOCX на базе docxtpl."""

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self.templates_dir = Path(templates_dir) if templates_dir else base_dir / "templates"

    def _create_default_tk_template(self, template_path: Path) -> None:
        """Создать минимальный tk_template.docx, если бинарный шаблон отсутствует."""
        template_path.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()
        doc.add_heading("ТЕХНОЛОГИЧЕСКАЯ КАРТА на {{work_type}}", level=1)

        doc.add_heading("1. Область применения", level=2)
        doc.add_paragraph("{{scope}}")

        doc.add_heading("2. Организация и технология производства работ", level=2)
        doc.add_paragraph("{{technology}}")

        doc.add_heading("3. Требования к качеству работ", level=2)
        doc.add_paragraph("{{quality_requirements}}")

        doc.add_heading("4. Нормативные документы", level=2)
        doc.add_paragraph(
            "{% for doc_name in normative_docs %}"
            "• {{doc_name}}"
            "{% if not loop.last %}\n{% endif %}"
            "{% endfor %}"
        )

        footer = doc.sections[0].footer
        footer.paragraphs[0].text = "ГОСТ Р 21.1101 · SHA256: {{sha256}}"
        doc.save(template_path)

    def _ensure_template(self, template_name: str) -> Path:
        template_path = self.templates_dir / f"{template_name}.docx"
        if template_path.exists():
            return template_path

        if template_name == "tk_template":
            self._create_default_tk_template(template_path)
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

    def list_templates(self) -> list[str]:
        """Список доступных DOCX-шаблонов (без расширения)."""
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        templates = {
            path.stem for path in self.templates_dir.glob("*.docx") if path.is_file()
        }
        templates.add("tk_template")
        return sorted(templates)
