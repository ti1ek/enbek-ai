"""Annual budget norms for Kazakhstan labor law calculations.

Source: Закон РК от 08.12.2025 № 239-VIII «О республиканском бюджете на 2026–2028 годы»
        https://adilet.zan.kz/rus/docs/Z2500000239
"""

NORMS: dict[int, dict] = {
    2026: {
        "mrp_kzt": 4_325,
        "min_wage_kzt": 85_000,
        "living_wage_kzt": 50_851,
        "source_url": "https://adilet.zan.kz/rus/docs/Z2500000239",
        "source_law": "Закон РК от 08.12.2025 № 239-VIII «О республиканском бюджете на 2026–2028 годы»",
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
    },
    2025: {
        "mrp_kzt": 3_932,
        "min_wage_kzt": 85_000,
        "living_wage_kzt": 43_407,
        "source_url": "https://adilet.zan.kz/rus/docs/Z2400000126",
        "source_law": "Закон РК от 28.11.2024 № 126-VIII «О республиканском бюджете на 2025–2027 годы»",
        "valid_from": "2025-01-01",
        "valid_until": "2025-12-31",
    },
    2024: {
        "mrp_kzt": 3_692,
        "min_wage_kzt": 85_000,
        "living_wage_kzt": 40_567,
        "source_url": "https://adilet.zan.kz/rus/docs/Z2300000218",
        "source_law": "Закон РК от 01.12.2023 № 218-VIII «О республиканском бюджете на 2024–2026 годы»",
        "valid_from": "2024-01-01",
        "valid_until": "2024-12-31",
    },
}

CURRENT_YEAR = 2026
CURRENT = NORMS[CURRENT_YEAR]

# Keywords that trigger norms injection into LLM context
SALARY_KEYWORDS = [
    "зарплат", "оклад", "мрп", "мзп", "мрот", "прожиточн", "минимальн",
    "штраф", "пособи", "выплат", "расчёт", "расчет", "исчислен",
    "задолженност", "компенсаци", "среднемесячн", "среднедневн",
]


def is_salary_related(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in SALARY_KEYWORDS)


def get_norms_context(year: int = CURRENT_YEAR) -> str:
    """Return formatted norms string for injection into LLM context."""
    n = NORMS.get(year, CURRENT)
    return (
        f"Действующие нормативы РК на {year} год:\n"
        f"— МРП (месячный расчётный показатель): {n['mrp_kzt']:,} тенге\n"
        f"— МЗП (минимальная заработная плата): {n['min_wage_kzt']:,} тенге\n"
        f"— Прожиточный минимум: {n['living_wage_kzt']:,} тенге\n"
        f"Источник: {n['source_law']}"
    )
