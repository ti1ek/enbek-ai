"""Extract citation edges (пункт↔пункт, статья↔статья) from chunk text.

Regex-based. Targets four patterns in KZ legal Russian:
  • intra-doc point   : "согласно пункту 7 настоящих Правил/приказа/постановления"
  • intra-doc article : "в порядке, установленном статьей 96 настоящего Кодекса"
  • TK RK article     : "в соответствии со статьёй 96 Трудового кодекса"
  • cross-doc decree  : "Постановлением Правительства РК от ... № 1406"
                       "Приказом Министра труда ... № 504"

Each edge: {source_chunk_id, target_doc_id, target_article, target_point, edge_type, raw_text}.
Sidecar file (not Qdrant) so the build is reversible.
"""
import re

# Capture group 1 = number (allow forms like "7", "15", "7-1")
_NUM = r"(\d+(?:-\d+)?)"

# "пункт(а/ом/у/е/ах) N" — case-insensitive, multi-form
_POINT_RE = re.compile(
    (r"пункт(?:а|ом|у|е|ами|ах|ов)?\s+" + _NUM
     + r"(?:\s+(настоящих|настоящего|данного|данных|настоящ\w*))?"
     + r"(?:\s+(Правил|Приказа|Постановления|Положения|Инструкции))?"),
    re.IGNORECASE,
)

# "статья N", "статьи N", "статьёй N", "статьей N"
_ARTICLE_RE = re.compile(
    (r"стать(?:я|и|ёй|ей|ю|е)\s+" + _NUM
     + r"(?:\s+(настоящего|Трудового|Гражданского|Социального))?"),
    re.IGNORECASE,
)

# "Постановлением (Правительства) ... № NNN"
_DECREE_RE = re.compile(
    (r"постановлени(?:я|ем|и|е)?\s+(?:Правительства\s+(?:Республики\s+Казахстан|РК)\s+)?"
     + r"(?:от\s+[^№]+)?№\s*" + _NUM),
    re.IGNORECASE,
)

# "Приказ(ом) Министра ... № NNN"
_ORDER_RE = re.compile(
    r"приказ(?:а|ом|у)?\s+Министра\s+[^№]+№\s*" + _NUM,
    re.IGNORECASE,
)


def extract_citations(chunk: dict) -> list[dict]:
    """Extract citation edges from a chunk's text.

    Args:
        chunk: {id, text, doc_id, article, paragraph, source_type, ...}

    Returns:
        List of edge dicts. Empty if nothing found.
    """
    text = chunk.get("text") or ""
    src_id = chunk.get("id")
    src_doc = chunk.get("doc_id") or ""
    src_type = chunk.get("source_type") or ""
    if not text or not src_id:
        return []

    edges: list[dict] = []
    seen: set[tuple] = set()

    def _add(target_doc_id: str, target_article: str, target_point: str,
             edge_type: str, raw: str) -> None:
        # Self-reference filter
        if (target_doc_id == src_doc
                and str(target_article) == str(chunk.get("article", ""))
                and str(target_point) == str(chunk.get("paragraph", ""))):
            return
        key = (target_doc_id, target_article, target_point, edge_type)
        if key in seen:
            return
        seen.add(key)
        edges.append({
            "source_chunk_id": src_id,
            "source_doc_id": src_doc,
            "target_doc_id": target_doc_id,
            "target_article": target_article,
            "target_point": target_point,
            "edge_type": edge_type,
            "raw_text": raw[:120],
        })

    # 1) Intra-doc point reference ("пункт N настоящих Правил")
    for m in _POINT_RE.finditer(text):
        num = m.group(1)
        scope = (m.group(2) or "").lower()
        target_kind = (m.group(3) or "").lower()
        # Heuristic: count as intra-doc only if "настоящ..." anchor present
        # OR the source doc is itself a regulation (ministerial_order / government_decree)
        if scope.startswith("настоящ") or target_kind or src_type in {
            "ministerial_order", "government_decree",
        }:
            _add(src_doc, "", num, "point", m.group(0))

    # 2) Article reference
    for m in _ARTICLE_RE.finditer(text):
        num = m.group(1)
        anchor = (m.group(2) or "").lower()
        if anchor == "трудового":
            _add("K1500000414", num, "", "article", m.group(0))
        elif anchor == "социального":
            # Social Code in KZ: doc_id Z2300000224 (current as of 2023+).
            _add("Z2300000224", num, "", "article", m.group(0))
        elif anchor == "гражданского":
            _add("K940001000_", num, "", "article", m.group(0))
        else:
            # "статьи N настоящего" or bare "статьи N" inside a code chunk
            if src_type in {"labor_code", "social_code", "civil_code", "koap"}:
                _add(src_doc, num, "", "article", m.group(0))

    # 3) Cross-doc decree number
    for m in _DECREE_RE.finditer(text):
        num = m.group(1)
        # Map well-known decree numbers to Qdrant doc_ids
        target = _DECREE_LOOKUP.get(num, f"PP_{num}")
        _add(target, "", "", "decree", m.group(0))

    # 4) Cross-doc ministerial order number
    for m in _ORDER_RE.finditer(text):
        num = m.group(1)
        target = _ORDER_LOOKUP.get(num, f"PRIKAZ_{num}")
        _add(target, "", "", "order", m.group(0))

    return edges


# Known KZ regulations referenced often in TK chunks.
# Extend as we discover them in build runs.
_DECREE_LOOKUP = {
    "1406": "P1200001406",  # Правила исчисления средней заработной платы
}
_ORDER_LOOKUP = {
    "12533": "V1500012533",  # Приказ Минздрава 2015 №1239 (Правила средней ЗП — приложение)
    "504": "V2300504",       # Приказ Минтруда 2023 №504 (в редакции которого Правила)
}
