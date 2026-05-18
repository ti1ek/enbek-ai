"""PII masking for KZ labor documents before sending to cloud LLMs."""
import re
from typing import Any


# KZ IIN checksum validation weights
_IIN_WEIGHTS_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
_IIN_WEIGHTS_2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]


def _validate_iin_checksum(iin: str) -> bool:
    """Validate KZ IIN by Luhn-like checksum algorithm."""
    if len(iin) != 12 or not iin.isdigit():
        return False
    digits = [int(d) for d in iin]
    s1 = sum(w * d for w, d in zip(_IIN_WEIGHTS_1, digits[:11])) % 11
    if s1 == 10:
        s1 = sum(w * d for w, d in zip(_IIN_WEIGHTS_2, digits[:11])) % 11
    return s1 == digits[11]


# Regex patterns (order matters — more specific first)
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("IIN",    re.compile(r'\b\d{12}\b'), "[IIN_{idx}]"),
    ("PHONE",  re.compile(r'(?<!\d)(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)'), "[PHONE_{idx}]"),
    ("EMAIL",  re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'), "[EMAIL_{idx}]"),
    ("IBAN",   re.compile(r'\bKZ\d{2}[A-Z0-9]{3}\d{13}\b'), "[IBAN_{idx}]"),
    ("BIN",    re.compile(r'\b\d{12}\b'), "[BIN_{idx}]"),  # Same as IIN but validated differently
    ("NAME",   re.compile(
        r'\b([А-ЯЁA-Z][а-яёa-z]+(?:-[А-ЯЁA-Z][а-яёa-z]+)?)\s+'
        r'([А-ЯЁA-Z][а-яёa-z]+(?:-[А-ЯЁA-Z][а-яёa-z]+)?)\s+'
        r'([А-ЯЁA-Z][а-яёa-z]+(?:ич|на|вна|овна|евна)?)\b'
    ), "[PERSON_{idx}]"),
]


def mask_pii(text: str) -> dict[str, Any]:
    """Mask PII in text and return masked text + mapping for later restoration.

    Returns:
        {
            "masked_text": str,
            "mapping": {"[PERSON_1]": "Иванов Иван Иванович", ...},
            "stats": {"IIN": 0, "PHONE": 0, "EMAIL": 0, "NAME": 0, ...}
        }
    """
    mapping: dict[str, str] = {}
    stats: dict[str, int] = {k: 0 for k, _, _ in _PATTERNS}
    counters: dict[str, int] = {k: 0 for k, _, _ in _PATTERNS}
    result = text

    for pii_type, pattern, placeholder_tpl in _PATTERNS:
        matches = list(pattern.finditer(result))
        # Process in reverse to preserve positions
        for m in reversed(matches):
            original = m.group(0)
            # For IIN: validate checksum
            if pii_type == "IIN":
                if not _validate_iin_checksum(original):
                    continue
            # For BIN: skip if already masked as IIN (no overlap in practice)
            if pii_type == "BIN":
                if not original.isdigit() or _validate_iin_checksum(original):
                    continue

            counters[pii_type] += 1
            placeholder = placeholder_tpl.format(idx=counters[pii_type])
            mapping[placeholder] = original
            result = result[:m.start()] + placeholder + result[m.end():]

        stats[pii_type] = counters[pii_type]

    return {
        "masked_text": result,
        "mapping": mapping,
        "stats": stats,
    }
