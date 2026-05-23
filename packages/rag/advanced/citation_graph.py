"""Lazy singleton: load citation edges from sidecar files and expose lookups.

Two edge files:
  data/chunks/citation_edges.json     — intra-doc text citations (built by build_citation_graph)
  data/chunks/cross_doc_edges.json    — cross-doc article→chunk links (built by build_cross_doc_edges)
"""
import json
from collections import defaultdict
from pathlib import Path

_EDGES_FILE = Path("data/chunks/citation_edges.json")
_CROSS_DOC_FILE = Path("data/chunks/cross_doc_edges.json")

# Lazy-loaded caches
_BY_SOURCE: dict[str, list[dict]] | None = None
_LOADED = False

_CROSS_DOC: dict[tuple, list[dict]] | None = None  # (source_doc_id, article) → edges
_CROSS_DOC_LOADED = False


def _load() -> None:
    global _BY_SOURCE, _LOADED
    _LOADED = True
    if not _EDGES_FILE.exists():
        _BY_SOURCE = {}
        return
    try:
        raw = json.loads(_EDGES_FILE.read_text(encoding="utf-8"))
    except Exception:
        _BY_SOURCE = {}
        return
    by_src: dict[str, list[dict]] = defaultdict(list)
    for e in raw:
        sid = e.get("source_chunk_id")
        if sid is not None:
            by_src[str(sid)].append(e)
    _BY_SOURCE = dict(by_src)


def _load_cross_doc() -> None:
    global _CROSS_DOC, _CROSS_DOC_LOADED
    _CROSS_DOC_LOADED = True
    if not _CROSS_DOC_FILE.exists():
        _CROSS_DOC = {}
        return
    try:
        raw = json.loads(_CROSS_DOC_FILE.read_text(encoding="utf-8"))
    except Exception:
        _CROSS_DOC = {}
        return
    by_art: dict[tuple, list[dict]] = defaultdict(list)
    for e in raw:
        key = (e.get("source_doc_id", ""), str(e.get("source_article", "")))
        by_art[key].append(e)
    _CROSS_DOC = dict(by_art)


def edges_from(source_chunk_id: str | int) -> list[dict]:
    """All outgoing intra-doc citation edges from a given chunk id."""
    if not _LOADED:
        _load()
    return _BY_SOURCE.get(str(source_chunk_id), []) if _BY_SOURCE else []


def cross_doc_edges_for_article(source_doc_id: str, article: str) -> list[dict]:
    """Cross-document edges for a given code article.

    Returns edges pointing to specific chunks in regulatory docs that implement
    or detail this article.
    """
    if not _CROSS_DOC_LOADED:
        _load_cross_doc()
    if not _CROSS_DOC:
        return []
    return _CROSS_DOC.get((source_doc_id, str(article)), [])


def edge_count() -> int:
    if not _LOADED:
        _load()
    if not _BY_SOURCE:
        return 0
    return sum(len(v) for v in _BY_SOURCE.values())


def cross_doc_edge_count() -> int:
    if not _CROSS_DOC_LOADED:
        _load_cross_doc()
    if not _CROSS_DOC:
        return 0
    return sum(len(v) for v in _CROSS_DOC.values())
