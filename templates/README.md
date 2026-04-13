# Templates

В репозитории не храним бинарные `.docx` файлы.

`tk_template.docx` создаётся автоматически в рантайме классом `DocxGenerator`
при первом вызове `generate("tk_template", context)`.

`ks_template.docx` также создаётся автоматически в рантайме (или скриптом `python scripts/generate_ks_template.py`).

`ppr_template.docx` создаётся автоматически в рантайме классом `DocxGenerator`
при первом вызове `generate("ppr_template", context)`.
