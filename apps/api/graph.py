"""LangGraph multi-agent workflow for Enbek AI.

Nodes:
  classifier → (qa_branch | appeal_branch | out_of_scope)
  QA branch: rephraser → retriever → reranker → conflict_resolver → synthesizer → citation_guard → END
  Appeal branch: retriever → reranker → appeal → END
  citation_guard can loop back to synthesizer (max 3 iter)
  out_of_scope → END
"""
import datetime
import json
import logging
import os
import re
from typing import Annotated, TypedDict

logger = logging.getLogger(__name__)
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langsmith import traceable
from packages.config import settings
from packages.rag.embeddings import embed_query
from packages.rag.qdrant_client import dense_search, hybrid_search
from packages.rag.retrieval.reranker import rerank
from packages.rag.prompts import SYSTEM_LEGAL_RU, RAG_PROMPT_TEMPLATE, build_attachment_block

# ─── State ────────────────────────────────────────────────────────────────────

class GraphState(TypedDict):
    question: str
    history: list[dict]              # prior conversation turns [{role, content}] for follow-ups
    pipeline: str                    # basic | advanced
    attachment_text: str             # text extracted from a user-attached document (optional)
    classification: str              # qa | appeal_* | out_of_scope
    rephrased_query: str
    hyde_text: str
    chunks: list[dict]               # retrieved raw chunks
    reranked: list[dict]             # reranked chunks
    context: str                     # formatted context for LLM
    answer: str
    sources: list[dict]
    citations_valid: bool
    iter_count: int
    conflict_note: str               # conflict resolution note injected into context
    conflict_detected: bool          # True if MinTruD contradicts primary sources
    verifier_iterations: int         # Self-RAG retry counter (capped at 2)
    verifier_critique: str           # Last verifier critique text
    verifier_passed: bool            # True if verifier accepted draft or feature disabled
    verifier_retry_query: str        # Query used by retriever in next retry pass
    error: str


def _flag(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in ("1", "true", "yes", "on")


def _verifier_enabled() -> bool:
    return _flag("ENABLE_VERIFIER")


def _decompose_enabled() -> bool:
    return _flag("ENABLE_DECOMPOSE")


def _graph_expand_enabled() -> bool:
    return _flag("ENABLE_GRAPH_EXPAND")


def _strict_citation_guard_enabled() -> bool:
    return _flag("ENABLE_STRICT_CITATION_GUARD")


def _hybrid_enabled() -> bool:
    return os.environ.get("ENABLE_HYBRID", "true").strip().lower() not in ("0", "false", "no", "off")


def _hyde_enabled() -> bool:
    return os.environ.get("ENABLE_HYDE", "true").strip().lower() not in ("0", "false", "no", "off")


def _rerank_enabled() -> bool:
    return os.environ.get("ENABLE_RERANK", "true").strip().lower() not in ("0", "false", "no", "off")


_sparse_model = None
_sparse_unavailable = False


def _sparse_vector_for(query: str):
    """Build BM25 sparse vector via fastembed, or None if unavailable.

    Falls back gracefully if fastembed/BM25 is not installed or the collection
    has no sparse vectors populated.
    """
    global _sparse_model, _sparse_unavailable
    if _sparse_unavailable:
        return None
    if _sparse_model is None:
        try:
            from fastembed import SparseTextEmbedding
            _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        except Exception as e:
            logger.warning("fastembed/BM25 unavailable, disabling sparse: %s", e)
            _sparse_unavailable = True
            return None
    try:
        from qdrant_client import models as _qm
        sparse_emb = next(iter(_sparse_model.embed([query])))
        return _qm.SparseVector(
            indices=sparse_emb.indices.tolist(),
            values=sparse_emb.values.tolist(),
        )
    except Exception as e:
        logger.warning("Sparse vector build failed, disabling: %s", e)
        _sparse_unavailable = True
        return None


def _search(query_vector, sparse_query: str, **kwargs):
    """Route search through hybrid (if enabled and feasible) or dense."""
    if _hybrid_enabled():
        sparse_vec = _sparse_vector_for(sparse_query)
        if sparse_vec is not None:
            try:
                return hybrid_search(
                    query_vector=query_vector,
                    sparse_vector=sparse_vec,
                    top_k=kwargs.get("top_k", 10),
                    source_types=kwargs.get("source_types"),
                    in_force_only=kwargs.get("in_force_only", True),
                )
            except Exception as e:
                logger.warning("Hybrid search failed, falling back to dense: %s", e)
    return dense_search(query_vector=query_vector, **kwargs)


# ─── LLM ─────────────────────────────────────────────────────────────────────

_llm_4o = None
_llm_mini = None


def _build_chat(model: str, temperature: float):
    """OpenAI primary; on error LangChain falls back to Gemini (gemini-2.5-flash)."""
    primary = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=settings.openai_api_key,
    )
    if settings.gemini_api_key:
        fallback = ChatOpenAI(
            model=settings.fallback_llm_model,
            temperature=temperature,
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_api_base,
        )
        return primary.with_fallbacks([fallback])
    return primary


def get_llm():
    global _llm_4o
    if _llm_4o is None:
        _llm_4o = _build_chat(settings.llm_model, temperature=0.1)
    return _llm_4o


def get_llm_mini():
    global _llm_mini
    if _llm_mini is None:
        _llm_mini = _build_chat(settings.llm_mini_model, temperature=0.0)
    return _llm_mini


# ─── Conversation history helpers ─────────────────────────────────────────────

def _format_history(history: list[dict], max_turns: int = 6, max_content: int = 500) -> str:
    """Render recent turns as a compact transcript for prompts."""
    if not history:
        return ""
    lines: list[str] = []
    for h in history[-max_turns:]:
        role = "Пользователь" if h.get("role") == "user" else "Ассистент"
        content = (h.get("content") or "").strip()
        if len(content) > max_content:
            content = content[:max_content] + "…"
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _contextualize_question(question: str, history: list[dict]) -> str:
    """Rewrite a follow-up into a standalone question using the dialog history.

    Resolves pronouns/ellipsis («а если…», «а сколько тогда?») so retrieval and
    classification work as if the user asked a fresh, self-contained question.
    Falls back to the original question on any failure.
    """
    if not history:
        return question
    transcript = _format_history(history)
    if not transcript:
        return question
    prompt = (
        "Перепиши последний вопрос пользователя как самостоятельный вопрос, понятный "
        "без истории диалога. Раскрой местоимения и отсылки («а если», «это», «тогда», "
        "«а сколько») на основе контекста выше. Сохрани язык и исходный смысл, ничего не добавляй. "
        "Если вопрос уже самодостаточен — верни его без изменений.\n\n"
        f"История диалога:\n{transcript}\n\n"
        f"Последний вопрос: {question}\n\n"
        "Верни ТОЛЬКО переписанный вопрос, без пояснений и кавычек."
    )
    try:
        resp = get_llm_mini().invoke(prompt)
        standalone = (resp.content or "").strip().strip('"').strip()
        return standalone or question
    except Exception as e:
        logger.warning("question contextualization failed: %s", e)
        return question


# ─── Node: Classifier ─────────────────────────────────────────────────────────

_VALID_CLASSES = {
    "qa",
    "appeal_court", "appeal_commission", "appeal_labor_inspection",
    "out_of_scope",
}

def classifier_node(state: GraphState) -> GraphState:
    prompt = f"""Классифицируй запрос пользователя по одной из категорий:
- "qa" — вопрос о трудовом праве, расчёте зарплаты, отпускных, пособий
- "appeal_court" — подготовка искового заявления в суд по трудовому спору
- "appeal_commission" — подготовка обращения в согласительную комиссию по трудовым спорам
- "appeal_labor_inspection" — подготовка жалобы в трудовую инспекцию или прокуратуру
- "out_of_scope" — вопрос не связан с трудовым правом РК

Запрос: "{state['question']}"

Ответь ТОЛЬКО одним словом из списка: qa, appeal_court, appeal_commission, appeal_labor_inspection, out_of_scope"""

    response = get_llm_mini().invoke(prompt)
    cls = response.content.strip().lower()
    if cls not in _VALID_CLASSES:
        cls = "qa"
    return {**state, "classification": cls}


def route_after_classifier(state: GraphState) -> str:
    cls = state["classification"]
    if cls == "qa":
        return "rephraser" if state.get("pipeline") == "advanced" else "retriever"
    elif cls == "out_of_scope":
        return "out_of_scope"
    else:  # appeal_*
        return "retriever"


# ─── Node: Rephraser (Advanced only) ─────────────────────────────────────────

def rephraser_node(state: GraphState) -> GraphState:
    from packages.rag.advanced.query_rephraser import rephrase_query
    rephrased = rephrase_query(state["question"])
    return {
        **state,
        "rephrased_query": rephrased["canonical"],
        "hyde_text": rephrased["hyde"],
    }


# ─── Node: Retriever ──────────────────────────────────────────────────────────

def _extract_year(text: str) -> int | None:
    """Extract a past year mention from text (2020-2025), if any."""
    current_year = datetime.date.today().year
    matches = re.findall(r"\b(20\d{2})\b", text)
    for m in matches:
        y = int(m)
        if 2020 <= y < current_year:
            return y
    return None


def _plan_hop2_queries(question: str, hop1_hits: list) -> list[str]:
    """LLM-mini читает найденные нормы кодекса и генерирует поисковые запросы
    для подзаконных актов (приказы, постановления) и НП ВС.
    Обобщённо — не хардкод под конкретные слова."""
    if not hop1_hits:
        return [question]
    hop1_summary = "\n".join(
        f"ст. {h.payload.get('article', '?')} {h.payload.get('source_type', '')}: "
        f"{h.payload.get('text', '')[:250]}"
        for h in hop1_hits[:3] if h.payload
    )
    prompt = (
        f"Вопрос: {question}\n\n"
        f"Найденные нормы кодекса:\n{hop1_summary}\n\n"
        "Определи какие подзаконные акты (приказы, постановления, правила) "
        "или нормативные постановления Верховного суда нужно проверить, "
        "чтобы найти конкретный порядок расчёта или применения нормы.\n"
        "Ответь 2-3 короткими поисковыми запросами на русском, каждый с новой строки. "
        "Только запросы, без пояснений."
    )
    try:
        resp = get_llm_mini().invoke(prompt)
        queries = [q.strip("•-– ") for q in resp.content.strip().split("\n") if q.strip()]
        return queries[:3] or [question]
    except Exception as e:
        logger.warning("hop2 query planning failed, using original question: %s", e)
        return [question]


def retriever_node(state: GraphState) -> GraphState:
    """3-hop retrieval:
    Hop 1 — ТК РК / Социальный кодекс (основа)
    Hop 2 — Приказы Минтруда (Правила расчётов) + НП ВС, запрос обогащён текстом из hop1
    Hop 3 — MinTrud Q&A как подтверждение/опровержение
    """
    year = _extract_year(state["question"])
    in_force = year is None
    is_verifier_retry = state.get("verifier_iterations", 0) > 0 and bool(state.get("verifier_retry_query"))

    # Hop1 — canonical/rephrased query (точнее попадает в статьи кодекса, чем HyDE).
    hop1_query = state.get("rephrased_query") or state["question"]
    hop1_vector = embed_query(hop1_query)

    # HyDE-вектор для hop3 (широкий семантический поиск подтверждений)
    if _hyde_enabled() and state.get("hyde_text") and state.get("hyde_text") != state["question"]:
        hyde_vector = embed_query(state["hyde_text"])
        q_vector = [(a + b) / 2 for a, b in zip(hyde_vector, embed_query(state["question"]))]
    else:
        q_vector = hop1_vector

    # ── Hop 1: первичное законодательство ─────────────────────────────────────
    hop1 = _search(
        query_vector=hop1_vector,
        sparse_query=hop1_query,
        top_k=3,
        source_types=["labor_code", "social_code"],
        in_force_only=in_force,
        redaction_year=year,
    )
    # Decomposition: run extra hop1 for each entity-focused sub-question.
    if _decompose_enabled() and not is_verifier_retry:
        from packages.rag.advanced.query_rephraser import decompose_question
        subs = decompose_question(state["question"])
        seen_hop1_ids = {h.id for h in hop1}
        for sub in subs:
            if sub.strip().lower() == hop1_query.strip().lower():
                continue
            sub_vec = embed_query(sub)
            for h in dense_search(
                query_vector=sub_vec,
                top_k=2,
                source_types=["labor_code", "social_code"],
                in_force_only=in_force,
                redaction_year=year,
            ):
                if h.id not in seen_hop1_ids:
                    seen_hop1_ids.add(h.id)
                    hop1.append(h)
    # Verifier retry mode: extra targeted search across подзаконка + НП ВС for the missing norm.
    hop1_retry: list = []
    if is_verifier_retry:
        retry_vector = embed_query(state["verifier_retry_query"])
        hop1_retry = dense_search(
            query_vector=retry_vector,
            top_k=4,
            source_types=["government_decree", "ministerial_order", "sc_decree",
                          "labor_code_commentary", "mintrud_guidelines"],
            in_force_only=False,
        )

    # ── Hop 2: подзаконные акты + НП ВС ──────────────────────────────────────
    # LLM-mini планировщик: читает hop1 и генерирует целевые запросы для приказов/НП
    hop2_queries = _plan_hop2_queries(state["question"], hop1)

    hop2_orders = []
    hop2_np = []
    seen_hop2: set = set()
    for q2 in hop2_queries:
        v2 = embed_query(q2)
        for hit in _search(query_vector=v2, sparse_query=q2, top_k=3, source_types=["ministerial_order", "government_decree"], in_force_only=False):
            if hit.id not in seen_hop2:
                seen_hop2.add(hit.id)
                hop2_orders.append(hit)
        for hit in _search(query_vector=v2, sparse_query=q2, top_k=1, source_types=["sc_decree", "labor_code_commentary"], in_force_only=False):
            if hit.id not in seen_hop2:
                seen_hop2.add(hit.id)
                hop2_np.append(hit)

    # ── Hop 3: MinTrud Q&A — подтверждение, проверяется против кодекса ────────
    hop3 = dense_search(
        query_vector=q_vector,
        top_k=3,
        source_types=["mintrud_dialog", "mintrud_faq", "mintrud_guidelines"],
        in_force_only=False,
    )

    # Merge: hop1 → hop1_retry → hop2 → hop3 (без дублей, кодекс всегда первым)
    seen_ids: set = set()
    merged = []
    for h in hop1 + hop1_retry + hop2_orders + hop2_np + hop3:
        if h.id not in seen_ids and h.payload:
            seen_ids.add(h.id)
            merged.append(h)

    chunks = [{"text": h.payload.get("text", ""), **h.payload, "_id": h.id}
              for h in merged]

    # Graph expansion: pull linked chunks from Qdrant payload (linked_chunks field).
    if _graph_expand_enabled() and chunks:
        from packages.rag.qdrant_client import fetch_chunk_by_id

        existing_keys = {
            (c.get("source_type"), str(c.get("article", "")),
             str(c.get("paragraph", "")), c.get("url", ""))
            for c in chunks
        }
        expanded: list[dict] = []
        budget = 6  # cap total graph-expansion fetches per request

        for c in list(chunks):
            if budget <= 0:
                break
            if c.get("source_type") not in {"labor_code", "social_code"}:
                continue
            for target_id in c.get("linked_chunks", []):
                if budget <= 0:
                    break
                t = fetch_chunk_by_id(target_id)
                if not t:
                    continue
                key = (t.get("source_type"), str(t.get("article", "")),
                       str(t.get("paragraph", "")), t.get("url", ""))
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                t["_id"] = t.get("id")
                t.pop("id", None)
                t["_graph_expanded"] = True
                expanded.append(t)
                budget -= 1

        chunks = expanded + chunks

    # Verifier retry: merge with prior chunks (dedupe by source_type+article+paragraph+url).
    if is_verifier_retry and state.get("chunks"):
        def _key(c: dict) -> tuple:
            return (c.get("source_type"), str(c.get("article", "")),
                    str(c.get("paragraph", "")), c.get("url", ""))
        seen_keys = set()
        merged_chunks: list[dict] = []
        for c in state["chunks"]:
            k = _key(c)
            if k not in seen_keys:
                seen_keys.add(k)
                merged_chunks.append(c)
        for c in chunks:
            k = _key(c)
            if k not in seen_keys:
                seen_keys.add(k)
                merged_chunks.append(c)
        chunks = merged_chunks

    return {**state, "chunks": chunks}


# ─── Node: Reranker (Advanced only) ───────────────────────────────────────────

_PRIMARY_TYPES = {"labor_code", "social_code", "koap", "civil_code",
                  "law", "government_decree", "ministerial_order"}
_SECONDARY_TYPES = {"sc_decree", "labor_code_commentary", "mintrud_guidelines", "annual_norms"}


def reranker_node(state: GraphState) -> GraphState:
    if not state.get("chunks"):
        return {**state, "reranked": []}

    chunks = state["chunks"]

    if not _rerank_enabled():
        return {**state, "reranked": chunks[:5]}

    n_primary, n_secondary = (4, 2) if _graph_expand_enabled() else (3, 1)
    pinned = [c for c in chunks if c.get("source_type") in _PRIMARY_TYPES][:n_primary]
    pinned += [c for c in chunks if c.get("source_type") in _SECONDARY_TYPES][:n_secondary]
    pinned_ids = {id(c) for c in pinned}
    rerank_pool = [c for c in chunks if id(c) not in pinned_ids]

    query = state.get("rephrased_query") or state["question"]
    reranked_pool = rerank(query=query, documents=rerank_pool, top_n=4)

    reranked = pinned + (reranked_pool or rerank_pool[:4])
    return {**state, "reranked": reranked}


# ─── Node: Conflict Resolver ─────────────────────────────────────────────────


def _find_old_qa_articles(docs: list[dict]) -> dict[str, list[str]]:
    """For Q&A answers dated before 2015 (old ТК 2007 era), extract cited article numbers.

    Returns {article_num: [qa_year, ...]} for articles that need cross-referencing.
    """
    result: dict[str, list[str]] = {}
    for d in docs:
        if d.get("source_type") != "mintrud_dialog":
            continue
        year = d.get("year") or 0
        if not year or year >= 2015:
            continue
        # Extract article numbers cited in the answer text
        arts = re.findall(r"ст\.?\s*(\d+[-\d]*)", d.get("text", ""))
        for art in arts:
            result.setdefault(art, [])
            if str(year) not in result[art]:
                result[art].append(str(year))
    return result


def _lookup_current_articles(article_nums: list[str]) -> dict[str, str]:
    """Search current ТК РК (K1500000414) for given article numbers.

    Returns {article_num: snippet} for articles found in the current code.
    """
    from packages.rag.qdrant_client import get_qdrant, COLLECTION
    from qdrant_client import models as qm

    qdrant = get_qdrant()
    found: dict[str, str] = {}

    for art in article_nums:
        try:
            result, _ = qdrant.scroll(
                collection_name=COLLECTION,
                scroll_filter=qm.Filter(must=[
                    qm.FieldCondition(key="doc_id", match=qm.MatchValue(value="K1500000414")),
                    qm.FieldCondition(key="article", match=qm.MatchValue(value=art)),
                    qm.FieldCondition(key="in_force", match=qm.MatchValue(value=True)),
                ]),
                limit=1,
                with_payload=["text", "parent_text"],
                with_vectors=False,
            )
            if result:
                snippet = (result[0].payload.get("text") or "")[:200]
                found[art] = snippet
        except Exception as e:
            logger.warning("_lookup_current_articles failed for art=%s: %s", art, e)

    return found


def conflict_resolver_node(state: GraphState) -> GraphState:
    """Detect conflicts between sources and annotate context with priority note."""
    docs = state.get("reranked") or state.get("chunks", [])
    if len(docs) < 2:
        return {**state, "conflict_note": ""}

    by_source: dict[str, list[dict]] = {}
    for d in docs:
        st = d.get("source_type", "unknown")
        by_source.setdefault(st, []).append(d)

    source_types = set(by_source.keys())
    has_law = bool(source_types & {"labor_code", "social_code"})
    has_qa = "mintrud_dialog" in source_types

    notes: list[str] = []

    has_np = "sc_decree" in source_types
    has_orders = bool(source_types & {"ministerial_order", "government_decree"})

    if has_law and has_qa:
        # Collect primary source texts (кодекс + приказы) and MinTruD texts
        primary_docs = [d for d in docs if d.get("source_type") in
                        {"labor_code", "social_code", "ministerial_order", "government_decree",
                         "labor_code_commentary", "mintrud_guidelines", "sc_decree"}]
        qa_docs = [d for d in docs if d.get("source_type") in {"mintrud_dialog", "mintrud_faq"}]

        # Ask LLM-mini to detect specific contradiction between primary and MinTruD
        if primary_docs and qa_docs:
            primary_snippet = "\n---\n".join(
                f"[{d.get('source_type','').upper()} ст.{d.get('article','')}]: {d.get('text','')[:300]}"
                for d in primary_docs[:3]
            )
            qa_snippet = "\n---\n".join(
                f"[МИНТРУД]: {d.get('text','')[:300]}"
                for d in qa_docs[:2]
            )
            conflict_prompt = (
                "Сравни эти два набора источников и определи: есть ли конкретное противоречие "
                "между нормой/приказом и ответом Минтруда?\n\n"
                f"НОРМЫ/ПРИКАЗЫ:\n{primary_snippet}\n\n"
                f"ОТВЕТЫ МИНТРУДА:\n{qa_snippet}\n\n"
                "Если противоречие есть — опиши его в 1-2 предложениях: что именно говорит норма/приказ "
                "и что говорит Минтруд, и почему приоритет у нормы/приказа. "
                "Если противоречия нет — ответь: НЕТ."
            )
            try:
                resp = get_llm_mini().invoke(conflict_prompt)
                conflict_text = resp.content.strip()
                if conflict_text.upper().startswith("НЕТ"):
                    notes.append(
                        "⚖️ Разъяснения Минтруда подтверждают позицию кодекса/подзаконных актов."
                    )
                    return {**state, "conflict_note": "\n\n".join(notes), "conflict_detected": False}
                else:
                    # Contradiction found — MinTruD will be excluded from context in synthesizer
                    return {**state, "conflict_note": "\n\n".join(notes), "conflict_detected": True}
            except Exception as e:
                logger.warning("conflict_resolver LLM call failed: %s", e)

    if has_np:
        notes.append(
            "📋 НП Верховного суда РК — обязательное толкование для судебной практики. "
            "Применяй наравне с кодексом при разрешении спорных ситуаций."
        )

    if has_orders:
        notes.append(
            "📑 Приказ/Постановление — подзаконный акт, детализирует порядок применения норм кодекса. "
            "Приоритет: Кодекс → Постановление → Приказ → НП ВС → Минтруд."
        )

    # Cross-reference old Q&A (pre-2015, ТК 2007 era) with current ТК РК
    old_arts = _find_old_qa_articles(docs)
    if old_arts:
        current = _lookup_current_articles(list(old_arts.keys()))
        lines = []
        for art, years in old_arts.items():
            year_str = ", ".join(years)
            if art in current:
                lines.append(
                    f"• Ст. {art} (упомянута в ответе от {year_str} г. по ТК 2007) — "
                    f"в действующем ТК РК 2015 статья {art} существует: «{current[art][:120]}...»"
                )
            else:
                lines.append(
                    f"• Ст. {art} (упомянута в ответе от {year_str} г.) — "
                    f"в действующем ТК РК 2015 статья {art} не найдена; норма могла быть перенесена или изменена."
                )
        notes.append(
            "⏳ Внимание: часть источников — ответы Минтруда, датированные до 2015 г. "
            "(эпоха старого ТК 2007). Номера статей могли измениться в ТК РК 2015:\n"
            + "\n".join(lines)
        )

    return {**state, "conflict_note": "\n\n".join(notes), "conflict_detected": False}


# ─── Node: Build Context ──────────────────────────────────────────────────────

_SECTION_LABELS: dict[str, str] = {
    "labor_code": "КОДЕКС — Трудовой кодекс РК",
    "social_code": "КОДЕКС — Социальный кодекс РК",
    "koap": "КОДЕКС — КоАП РК",
    "civil_code": "КОДЕКС — Гражданский кодекс РК",
    "law": "ЗАКОН РК",
    "government_decree": "ПОСТАНОВЛЕНИЕ ПРАВИТЕЛЬСТВА РК",
    "ministerial_order": "ПРИКАЗ МИНИСТЕРСТВА ТРУДА РК",
    "sc_decree": "НП ВЕРХОВНОГО СУДА РК",
    "mintrud_dialog": "РАЗЪЯСНЕНИЕ МИНТРУДА РК",
    "mintrud_faq": "РАЗЪЯСНЕНИЕ МИНТРУДА РК",
    "mintrud_guidelines": "МЕТОДИЧЕСКИЕ РЕКОМЕНДАЦИИ МИНТРУДА РК",
    "labor_code_commentary": "КОММЕНТАРИЙ К ТК РК",
}

def _make_link_text(st: str, art: str, doc: dict) -> str:
    """Build human-readable link label for a chunk."""
    if st == "labor_code":
        return f"ст. {art} ТК РК" if art and art != "0" else "ТК РК"
    if st == "social_code":
        return f"ст. {art} Социального кодекса РК" if art and art != "0" else "Социального кодекса РК"
    if st == "koap":
        return f"ст. {art} КоАП РК" if art and art != "0" else "КоАП РК"
    if st in {"ministerial_order", "government_decree"}:
        doc_name = doc.get("doc_name", "Приказа")
        # paragraph field is internal ID (block_N) — extract real number from text start
        text = doc.get("text", "")
        m = re.match(r"^(\d+)[.\)]", text.strip())
        para_num = m.group(1) if m else ""
        return f"п. {para_num} {doc_name}" if para_num else doc_name
    if st in {"mintrud_dialog", "mintrud_faq"}:
        return "Разъяснение Минтруда РК"
    if st == "sc_decree":
        return "НП ВС РК"
    return _SECTION_LABELS.get(st, st)


def build_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    # Slot-based selection — каждая группа источников имеет свой лимит слотов
    _CODES = {"labor_code", "social_code", "koap", "civil_code", "law"}
    _SUBLAWS = {"ministerial_order", "government_decree"}      # Приказы, Правила расчётов
    _SECONDARY = {"sc_decree", "labor_code_commentary", "mintrud_guidelines", "annual_norms"}
    _CONFIRMATION = {"mintrud_dialog", "mintrud_faq"}

    sublaw_slots = 3 if _graph_expand_enabled() else 2
    selected: list[dict] = []
    codes_seen = sublaws_seen = secondary_seen = 0
    for doc in chunks:
        st = doc.get("source_type", "other")
        if st in _CODES and codes_seen < 2:
            selected.append(doc); codes_seen += 1
        elif st in _SUBLAWS and sublaws_seen < sublaw_slots:
            selected.append(doc); sublaws_seen += 1
        elif st in _SECONDARY and secondary_seen < 2:
            selected.append(doc); secondary_seen += 1
    # Fill remaining slots (up to 8 total) with MinTruд confirmation
    for doc in chunks:
        if len(selected) >= 8:
            break
        if doc.get("source_type") in _CONFIRMATION and doc not in selected:
            selected.append(doc)
    # Pad with anything else not yet added
    for doc in chunks:
        if len(selected) >= 8:
            break
        if doc not in selected:
            selected.append(doc)

    priority = [
        "labor_code", "social_code", "koap", "civil_code",
        "sc_decree", "law", "government_decree", "ministerial_order",
        "labor_code_commentary", "mintrud_dialog", "mintrud_faq", "mintrud_guidelines",
    ]
    grouped: dict[str, list[dict]] = {}
    for doc in selected:
        st = doc.get("source_type", "other")
        grouped.setdefault(st, []).append(doc)

    context_parts = []
    sources = []

    for st in priority:
        if st not in grouped:
            continue
        for doc in grouped[st]:
            ctx = doc.get("parent_text") or doc.get("text", "")
            url = doc.get("url") if not doc.get("inactive_count", 0) else None
            label = _SECTION_LABELS.get(st, st.upper())
            art = doc.get("article", "")
            para = doc.get("paragraph", "")
            header = f"[{label}{' | ст.' + art if art else ''}]"
            url_hint = ""
            if url:
                url_hint = f"\n→ Ссылка: [{_make_link_text(st, art, doc)}]({url})"
            context_parts.append(f"{header}{url_hint}\n{ctx}")
            sources.append({
                "source_type": st,
                "label": _SECTION_LABELS.get(st, st),
                "article": art,
                "paragraph": doc.get("paragraph"),
                "url": url,
                "doc_name": doc.get("doc_name"),
            })

    # Any remaining source types not in priority list
    for st, docs in grouped.items():
        if st in priority:
            continue
        for doc in docs:
            ctx = doc.get("parent_text") or doc.get("text", "")
            url = doc.get("url") if not doc.get("inactive_count", 0) else None
            context_parts.append(f"[{st.upper()}]\n{ctx}")
            sources.append({
                "source_type": st,
                "label": st.upper(),
                "article": doc.get("article", ""),
                "paragraph": doc.get("paragraph"),
                "url": url,
                "doc_name": doc.get("doc_name"),
            })

    return "\n\n---\n\n".join(context_parts) if context_parts else "Контекст не найден.", sources


# ─── Node: Synthesizer ────────────────────────────────────────────────────────

_MINTRUD_QA_TYPES = {"mintrud_dialog", "mintrud_faq"}

def synthesizer_node(state: GraphState) -> GraphState:
    docs = state.get("reranked") or state.get("chunks", [])
    # If MinTruD contradicts primary sources — exclude it from context entirely
    if state.get("conflict_detected"):
        docs = [d for d in docs if d.get("source_type") not in _MINTRUD_QA_TYPES]
    context, sources = build_context(docs)

    if state.get("conflict_note"):
        context = context + "\n\n---\n\n" + state["conflict_note"]

    attachment_block = build_attachment_block(state.get("attachment_text", ""))
    if attachment_block:
        context = attachment_block + "\n\n---\n\n" + context

    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=state["question"])
    transcript = _format_history(state.get("history", []))
    if transcript:
        prompt = (
            "Это продолжение диалога. Ниже — предыдущие реплики (контекст, НЕ источник права). "
            "Учитывай их, но отвечай на текущий вопрос; не повторяй уже сказанное дословно.\n\n"
            f"ПРЕДЫДУЩИЙ ДИАЛОГ:\n{transcript}\n\n---\n\n"
        ) + prompt
    response = get_llm_mini().invoke([
        {"role": "system", "content": SYSTEM_LEGAL_RU},
        {"role": "user", "content": prompt},
    ])
    return {
        **state,
        "answer": response.content,
        "sources": sources,
        "context": context,
    }


# ─── Node: Verifier (Self-RAG, behind ENABLE_VERIFIER) ───────────────────────

_VERIFIER_MAX_ITER = 2


def verifier_node(state: GraphState) -> GraphState:
    """Critique the synthesized draft. If it misses a more specific norm — request a retry.

    Disabled by default; activated by env var ENABLE_VERIFIER=true.
    """
    if not _verifier_enabled():
        return {**state, "verifier_passed": True, "verifier_retry_query": ""}

    iterations = state.get("verifier_iterations", 0)
    if iterations >= _VERIFIER_MAX_ITER:
        return {**state, "verifier_passed": True, "verifier_retry_query": ""}

    from packages.rag.advanced.verifier import critique_draft
    verdict = critique_draft(
        question=state["question"],
        draft=state.get("answer", ""),
        sources=state.get("sources", []),
        context=state.get("context", ""),
    )

    if verdict["is_valid"] or not verdict.get("retry_query"):
        return {
            **state,
            "verifier_passed": True,
            "verifier_critique": verdict.get("critique", ""),
            "verifier_retry_query": "",
        }

    return {
        **state,
        "verifier_passed": False,
        "verifier_critique": verdict.get("critique", ""),
        "verifier_retry_query": verdict["retry_query"],
        "verifier_iterations": iterations + 1,
    }


def route_after_verifier(state: GraphState) -> str:
    if state.get("verifier_passed"):
        return "citation_guard"
    return "retriever"


# ─── Node: Citation Guard ─────────────────────────────────────────────────────

_POINT_CITE_RE = re.compile(r"(?:п\.\s*|пункт(?:а|ом|у|е)?\s+)(\d+(?:-\d+)?)", re.IGNORECASE)


def citation_guard_node(state: GraphState) -> GraphState:
    """Check if cited articles (and, in strict mode, points) actually exist in retrieved context."""
    answer = state.get("answer", "")
    context = state.get("context", "")

    cited_arts = set(re.findall(r"ст\.\s*(\d+[-\d]*)", answer))
    context_arts = set(re.findall(r"ст\.(\d+[-\d]*)", context))

    valid = not cited_arts or bool(cited_arts & context_arts)

    if _strict_citation_guard_enabled() and valid:
        cited_points = {m.group(1) for m in _POINT_CITE_RE.finditer(answer)}
        if cited_points:
            context_points = {m.group(1) for m in _POINT_CITE_RE.finditer(context)}
            # Also accept points that appear as numeric prefixes "N." or "N)" in context
            for prefix in re.findall(r"(?:^|\n)\s*(\d+(?:-\d+)?)[.)]\s", context):
                context_points.add(prefix)
            if not (cited_points & context_points):
                valid = False

    return {
        **state,
        "citations_valid": valid,
        "iter_count": state.get("iter_count", 0) + 1,
    }


def route_after_citation_guard(state: GraphState) -> str:
    if state.get("citations_valid") or state.get("iter_count", 0) >= 3:
        return END
    return "synthesizer"


# ─── Node: Out of Scope ───────────────────────────────────────────────────────

def out_of_scope_node(state: GraphState) -> GraphState:
    return {
        **state,
        "answer": (
            "Этот вопрос выходит за рамки трудового законодательства Казахстана. "
            "Я специализируюсь на вопросах Трудового кодекса РК, Социального кодекса РК "
            "и связанных нормативных актов. Пожалуйста, задайте вопрос по трудовому праву."
        ),
        "sources": [],
    }


# ─── Node: Appeal ─────────────────────────────────────────────────────────────

_APPEAL_TEMPLATES = {
    "appeal_court": (
        "Составь исковое заявление в суд по трудовому спору на основании ТК РК.\n\n"
        "Правовая база из контекста:\n{context}\n\n"
        "Суть обращения: {question}\n\n"
        "Структура документа:\n"
        "1. Наименование суда (оставь поле для заполнения)\n"
        "2. Истец: ФИО, адрес (поле для заполнения)\n"
        "3. Ответчик: наименование работодателя, адрес (поле для заполнения)\n"
        "4. ИСКОВОЕ ЗАЯВЛЕНИЕ о [предмет иска]\n"
        "5. ОБСТОЯТЕЛЬСТВА ДЕЛА — изложи факты нарушения\n"
        "6. ПРАВОВОЕ ОБОСНОВАНИЕ — конкретные статьи ТК РК, НП ВС из контекста\n"
        "7. ИСКОВЫЕ ТРЕБОВАНИЯ — чёткий перечень требований\n"
        "8. ПРИЛОЖЕНИЯ — список документов\n"
        "9. Дата, подпись"
    ),
    "appeal_commission": (
        "Составь заявление в согласительную комиссию по трудовым спорам (ст. 159–169 ТК РК).\n\n"
        "Правовая база из контекста:\n{context}\n\n"
        "Суть обращения: {question}\n\n"
        "Структура документа:\n"
        "1. В согласительную комиссию [наименование организации]\n"
        "2. От работника: ФИО, должность (поле для заполнения)\n"
        "3. ЗАЯВЛЕНИЕ\n"
        "4. ОПИСАНИЕ СПОРА — факты и хронология нарушения\n"
        "5. ПРАВОВОЕ ОБОСНОВАНИЕ — статьи ТК РК из контекста\n"
        "6. ТРЕБОВАНИЯ к работодателю\n"
        "7. Дата, подпись"
    ),
    "appeal_labor_inspection": (
        "Составь жалобу в уполномоченный орган по труду (государственная трудовая инспекция, ст. 17 ТК РК) "
        "или прокуратуру.\n\n"
        "Правовая база из контекста:\n{context}\n\n"
        "Суть обращения: {question}\n\n"
        "Структура документа:\n"
        "1. Руководителю [наименование органа] (поле для заполнения)\n"
        "2. От: ФИО, адрес, телефон (поле для заполнения)\n"
        "3. ЖАЛОБА\n"
        "4. ФАКТЫ НАРУШЕНИЯ — конкретные действия/бездействие работодателя с датами\n"
        "5. НАРУШЕННЫЕ НОРМЫ — статьи ТК РК и НПА из контекста\n"
        "6. ПРОСЬБА — провести проверку, привлечь к ответственности, обязать устранить нарушения\n"
        "7. Приложения, дата, подпись"
    ),
}


def appeal_node(state: GraphState) -> GraphState:
    """Generate formal appeal document using retrieved legal context."""
    docs = state.get("reranked") or state.get("chunks", [])
    context, sources = build_context(docs)

    if state.get("conflict_note"):
        context = context + "\n\n---\n\n" + state["conflict_note"]

    attachment_block = build_attachment_block(state.get("attachment_text", ""))
    if attachment_block:
        context = attachment_block + "\n\n---\n\n" + context

    cls = state["classification"]
    template = _APPEAL_TEMPLATES.get(cls, _APPEAL_TEMPLATES["appeal_court"])
    prompt = template.format(context=context, question=state["question"])

    response = get_llm().invoke([
        {"role": "system", "content": SYSTEM_LEGAL_RU},
        {"role": "user", "content": prompt},
    ])
    return {
        **state,
        "answer": response.content,
        "sources": sources,
        "context": context,
    }


# ─── Build Graph ──────────────────────────────────────────────────────────────

def route_after_reranker(state: GraphState) -> str:
    cls = state["classification"]
    if cls in {"appeal_court", "appeal_commission", "appeal_labor_inspection"}:
        return "appeal"
    return "conflict_resolver"


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("classifier", classifier_node)
    g.add_node("rephraser", rephraser_node)
    g.add_node("retriever", retriever_node)
    g.add_node("reranker", reranker_node)
    g.add_node("conflict_resolver", conflict_resolver_node)
    g.add_node("synthesizer", synthesizer_node)
    g.add_node("verifier", verifier_node)
    g.add_node("citation_guard", citation_guard_node)
    g.add_node("out_of_scope", out_of_scope_node)
    g.add_node("appeal", appeal_node)

    g.set_entry_point("classifier")

    g.add_conditional_edges("classifier", route_after_classifier, {
        "rephraser": "rephraser",
        "retriever": "retriever",
        "out_of_scope": "out_of_scope",
    })

    g.add_edge("rephraser", "retriever")
    g.add_edge("retriever", "reranker")

    g.add_conditional_edges("reranker", route_after_reranker, {
        "conflict_resolver": "conflict_resolver",
        "appeal": "appeal",
    })

    g.add_edge("conflict_resolver", "synthesizer")
    g.add_edge("synthesizer", "verifier")

    g.add_conditional_edges("verifier", route_after_verifier, {
        "retriever": "retriever",
        "citation_guard": "citation_guard",
    })

    g.add_conditional_edges("citation_guard", route_after_citation_guard, {
        "synthesizer": "synthesizer",
        END: END,
    })

    g.add_edge("out_of_scope", END)
    g.add_edge("appeal", END)

    return g.compile()


# Singleton compiled graph
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


@traceable(name="langgraph_qa")
def run_graph(
    question: str,
    pipeline: str = "advanced",
    attachment_text: str = "",
    history: list[dict] | None = None,
) -> dict:
    history = history or []
    # Resolve follow-up references into a standalone question for retrieval/classification.
    standalone = _contextualize_question(question, history)
    graph = get_graph()
    initial_state: GraphState = {
        "question": standalone,
        "history": history,
        "pipeline": pipeline,
        "attachment_text": attachment_text,
        "classification": "",
        "rephrased_query": "",
        "hyde_text": "",
        "chunks": [],
        "reranked": [],
        "context": "",
        "answer": "",
        "sources": [],
        "citations_valid": False,
        "iter_count": 0,
        "conflict_note": "",
        "conflict_detected": False,
        "verifier_iterations": 0,
        "verifier_critique": "",
        "verifier_passed": False,
        "verifier_retry_query": "",
        "error": "",
    }
    final = graph.invoke(initial_state)
    return {
        "answer": final.get("answer", ""),
        "sources": final.get("sources", []),
        "context": final.get("context", ""),
        "classification": final.get("classification", ""),
        "pipeline": pipeline,
    }
