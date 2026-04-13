"""Тесты генератора DOCX."""

from core.docx_generator import DocxGenerator


def test_docx_generator_creates_non_empty_document(tmp_path) -> None:
    """DocxGenerator должен возвращать непустые bytes DOCX."""
    generator = DocxGenerator(templates_dir=tmp_path)

    payload = generator.generate(
        "tk_template",
        {
            "work_type": "монолитные работы",
            "scope": "Применяется при устройстве фундаментной плиты.",
            "technology": "Работы выполняются поэтапно с контролем бетона.",
            "quality_requirements": "Контроль прочности и геометрии конструкций.",
            "normative_docs": ["СП 70.13330", "ГОСТ 7473"],
            "sha256": "abc123",
        },
    )

    assert isinstance(payload, bytes)
    assert len(payload) > 0
    assert (tmp_path / "tk_template.docx").exists()
    assert "tk_template" in generator.list_templates()
