"""Annual budget norms for Kazakhstan — generates Qdrant chunks.

Values are stored in Qdrant as source_type="annual_norms" and retrieved
through normal semantic search when relevant to the user's question.

Source: Закон РК от 08.12.2025 № 239-VIII «О республиканском бюджете на 2026–2028 годы»
        https://adilet.zan.kz/rus/docs/Z2500000239
"""
import json
import uuid
from pathlib import Path

DATA_DIR = Path("data/chunks")

NORMS: dict[int, dict] = {
    2026: {
        "mrp_kzt": 4_325,
        "min_wage_kzt": 85_000,
        "living_wage_kzt": 50_851,
        "source_url": "https://adilet.zan.kz/rus/docs/Z2500000239",
        "source_law": "Закон РК от 08.12.2025 № 239-VIII «О республиканском бюджете на 2026–2028 годы»",
    },
    2025: {
        "mrp_kzt": 3_932,
        "min_wage_kzt": 85_000,
        "living_wage_kzt": 43_407,
        "source_url": "https://adilet.zan.kz/rus/docs/Z2400000126",
        "source_law": "Закон РК от 28.11.2024 № 126-VIII «О республиканском бюджете на 2025–2027 годы»",
    },
    2024: {
        "mrp_kzt": 3_692,
        "min_wage_kzt": 85_000,
        "living_wage_kzt": 40_567,
        "source_url": "https://adilet.zan.kz/rus/docs/Z2300000218",
        "source_law": "Закон РК от 01.12.2023 № 218-VIII «О республиканском бюджете на 2024–2026 годы»",
    },
}


def build_chunks() -> list[dict]:
    """Build Qdrant-ready chunks for annual norms of each year."""
    chunks = []
    for year, n in NORMS.items():
        in_force = (year == 2026)

        # One combined chunk per year — covers all three values together
        text = (
            f"Нормативы Республики Казахстан на {year} год:\n"
            f"МРП (месячный расчётный показатель) — {n['mrp_kzt']:,} тенге.\n"
            f"МЗП (минимальная заработная плата) — {n['min_wage_kzt']:,} тенге.\n"
            f"Прожиточный минимум — {n['living_wage_kzt']:,} тенге.\n"
            f"Источник: {n['source_law']}."
        )

        chunk_id = f"annual_norms_{year}"
        chunks.append({
            "chunk_id": chunk_id,
            "parent_id": chunk_id,
            "text": text,
            "parent_text": text,
            "source_type": "annual_norms",
            "doc_id": f"budget_law_{year}",
            "article": "",
            "paragraph": "",
            "redaction_date": f"{year}-01-01",
            "in_force": in_force,
            "url": n["source_url"],

            "doc_name": n["source_law"],
        })

        # Individual chunks per indicator for finer-grained retrieval
        indicators = [
            (
                "mrp",
                f"МРП (месячный расчётный показатель) на {year} год — {n['mrp_kzt']:,} тенге. "
                f"Применяется для расчёта штрафов по КоАП РК, госпошлин и иных выплат, "
                f"исчисляемых в МРП. Источник: {n['source_law']}."
            ),
            (
                "mzp",
                f"МЗП (минимальная заработная плата) на {year} год — {n['min_wage_kzt']:,} тенге. "
                f"Работодатель обязан выплачивать работнику зарплату не ниже МЗП (ст. 107 ТК РК). "
                f"Источник: {n['source_law']}."
            ),
            (
                "pm",
                f"Прожиточный минимум на {year} год — {n['living_wage_kzt']:,} тенге. "
                f"Используется для расчёта социальных пособий и минимальных пенсионных выплат. "
                f"Источник: {n['source_law']}."
            ),
        ]

        for key, ind_text in indicators:
            ind_id = f"annual_norms_{year}_{key}"
            chunks.append({
                "chunk_id": ind_id,
                "parent_id": chunk_id,
                "text": ind_text,
                "parent_text": text,
                "source_type": "annual_norms",
                "doc_id": f"budget_law_{year}",
                "article": "",
                "paragraph": key,
                "redaction_date": f"{year}-01-01",
                "in_force": in_force,
                "url": n["source_url"],
    
                "doc_name": n["source_law"],
            })

    return chunks


def save_chunks() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    chunks = build_chunks()
    out = DATA_DIR / "annual_norms.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(chunks)} annual norms chunks → {out}")
    return chunks


if __name__ == "__main__":
    save_chunks()
