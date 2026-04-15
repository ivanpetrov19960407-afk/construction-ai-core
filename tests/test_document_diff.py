"""Тесты сравнения версий документов."""

from core.document_diff import DocumentDiff


def test_compare_identical_texts_100pct():
    """Идентичные тексты должны давать 100% сходства и пустой diff."""
    service = DocumentDiff()
    text = "Раздел 1\nОбщие положения\nРаздел 2\nТехника безопасности"

    diff = service.compare_texts(text, text)

    assert diff["similarity_pct"] == 100.0
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["critical_changes"] == []


def test_compare_different_texts_detects_changes():
    """Разные тексты должны показывать добавленные/удалённые строки."""
    service = DocumentDiff()

    text_v1 = "Раздел 1\nБетонирование стен\nСрок: 5 дней"
    text_v2 = "Раздел 1\nБетонирование стен\nСрок: 7 дней\nНовая позиция"

    diff = service.compare_texts(text_v1, text_v2)

    assert diff["similarity_pct"] < 100.0
    assert "Срок: 7 дней" in diff["added"]
    assert "Срок: 5 дней" in diff["removed"]
    assert diff["changed_sections"]


def test_critical_change_detected_in_safety_section():
    """Изменения в разделе безопасности должны помечаться как критические."""
    service = DocumentDiff()

    text_v1 = "Техника безопасности\nИспользовать каски и страховочные привязи"
    text_v2 = "Техника безопасности\nКаски использовать по усмотрению"

    diff = service.compare_texts(text_v1, text_v2)
    report = service.generate_diff_report(diff)

    assert diff["critical_changes"]
    assert "Критические изменения" in report
