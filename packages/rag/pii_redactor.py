"""PII redactor: masks personal data before sending to external LLM APIs.

Detected types: ИИН/БИН, phone, email, date, full name (ФИО).
Replacement is one-way (Variant B) — originals are never restored.
"""
import re

# Order matters: more specific patterns first
_PATTERNS: list[tuple[str, str]] = [
    # ИИН / БИН — exactly 12 digits standalone
    (r'\b\d{12}\b', 'ИИН'),
    # Kazakh/Russian phone: +7 or 8 prefix
    (r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', 'ТЕЛЕФОН'),
    # Email
    (r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', 'EMAIL'),
    # Date DD.MM.YYYY (birth dates, document dates)
    (r'\b\d{2}\.\d{2}\.\d{4}\b', 'ДАТА'),
    # Full name with Russian/Kazakh patronymic: Фамилия Имя Отчество
    (
        r'\b[А-ЯЁ][а-яё]{1,20}\s[А-ЯЁ][а-яё]{1,20}\s[А-ЯЁ][а-яё]{1,15}'
        r'(?:ич|овна|евна|ична|улы|қызы)\b',
        'ФИО',
    ),
    # Initials + surname: И.И. Иванов
    (r'\b[А-ЯЁ]\.[А-ЯЁ]\.\s[А-ЯЁ][а-яё]{2,20}\b', 'ФИО'),
    # Surname + initials: Иванов И.И.
    (r'\b[А-ЯЁ][а-яё]{2,20}\s[А-ЯЁ]\.[А-ЯЁ]\.\b', 'ФИО'),
]

_COMPILED = [(re.compile(p), label) for p, label in _PATTERNS]


def mask_pii(text: str) -> str:
    """Replace PII in text with labeled placeholders like [ФИО_1], [ИИН_2]."""
    if not text:
        return text
    counters: dict[str, int] = {}
    result = text
    for rx, label in _COMPILED:
        def replacer(m: re.Match, lbl: str = label) -> str:
            counters[lbl] = counters.get(lbl, 0) + 1
            return f'[{lbl}_{counters[lbl]}]'
        result = rx.sub(replacer, result)
    return result
