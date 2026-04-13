# Templates

В репозитории **не храним** бинарные `.docx` файлы.

Все шаблоны создаются скриптом:

```bash
python scripts/generate_templates.py
```

Скрипт генерирует:
- `tk_template.docx`
- `letter_template.docx`
- `ks_template.docx`
- `ppr_template.docx`

`DocxGenerator` также автоматически запускает генерацию, если нужного шаблона нет в `templates/`.
