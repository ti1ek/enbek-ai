"""LangGraph multi-agent workflow for Enbek AI.

Nodes:
  classifier → (qa_branch | doc_branch | out_of_scope)
  QA branch: rephraser → retriever → reranker → conflict_resolver → synthesizer → citation_guard → END
  Doc branch: doc_processor → END
  citation_guard can loop back to synthesizer (max 3 iter)
  out_of_scope → END
"""
import json
import re
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langsmith import traceable
from packages.config import settings
from packages.rag.embeddings import embed_query
from packages.rag.qdrant_client import dense_search
from packages.rag.retrieval.reranker import rerank
from packages.rag.prompts import SYSTEM_LEGAL_RU, RAG_PROMPT_TEMPLATE

# ─── State ────────────────────────────────────────────────────────────────────

class GraphState(TypedDict):
    question: str
    pipeline: str                    # basic | advanced
    classification: str              # qa | doc_check | doc_fix | doc_improve | doc_generate | out_of_scope
    rephrased_query: str
    hyde_text: str
    chunks: list[dict]               # retrieved raw chunks
    reranked: list[dict]             # reranked chunks
    context: str                     # formatted context for LLM
    answer: str
    sources: list[dict]
    citations_valid: bool
    iter_count: int
    doc_text: str                    # extracted document text (for doc branch)
    doc_clauses: list[dict]          # parsed clauses [{type, text, compliant, norm, recommendation}]
    conflict_note: str               # conflict resolution note injected into context
    error: str


# ─── LLM ─────────────────────────────────────────────────────────────────────

_llm_4o = None
_llm_mini = None


def get_llm():
    global _llm_4o
    if _llm_4o is None:
        _llm_4o = ChatOpenAI(
            model="gpt-4.1",
            temperature=0.1,
            api_key=settings.openai_api_key,
        )
    return _llm_4o


def get_llm_mini():
    global _llm_mini
    if _llm_mini is None:
        _llm_mini = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0.0,
            api_key=settings.openai_api_key,
        )
    return _llm_mini


# ─── Node: Classifier ─────────────────────────────────────────────────────────

_VALID_CLASSES = {
    "qa", "doc_check", "doc_fix", "doc_generate",
    "appeal_court", "appeal_commission", "appeal_labor_inspection",
    "doc_analysis", "out_of_scope",
}

def classifier_node(state: GraphState) -> GraphState:
    prompt = f"""Классифицируй запрос пользователя по одной из категорий:
- "qa" — вопрос о трудовом праве, расчёте зарплаты, отпускных, пособий
- "doc_check" — проверка документа на соответствие ТК РК
- "doc_fix" — исправление или улучшение трудового документа
- "doc_generate" — создание нового трудового документа (договор, приказ, заявление)
- "doc_analysis" — анализ прикреплённого документа: что означает, права и обязанности сторон
- "appeal_court" — подготовка искового заявления в суд по трудовому спору
- "appeal_commission" — подготовка обращения в согласительную комиссию по трудовым спорам
- "appeal_labor_inspection" — подготовка жалобы в трудовую инспекцию или прокуратуру
- "out_of_scope" — вопрос не связан с трудовым правом РК

Запрос: "{state['question']}"

Ответь ТОЛЬКО одним словом из списка: qa, doc_check, doc_fix, doc_generate, doc_analysis, appeal_court, appeal_commission, appeal_labor_inspection, out_of_scope"""

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
    elif cls in {"appeal_court", "appeal_commission", "appeal_labor_inspection"}:
        return "retriever"
    elif cls == "doc_analysis":
        return "retriever" if state.get("doc_text") else "doc_processor"
    else:
        return "doc_processor"


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
    current_year = 2026
    matches = re.findall(r"\b(20\d{2})\b", text)
    for m in matches:
        y = int(m)
        if 2020 <= y < current_year:
            return y
    return None


def retriever_node(state: GraphState) -> GraphState:
    query = state.get("hyde_text") or state["question"]
    q_vector = embed_query(query)

    # If HyDE available, average with original
    if state.get("hyde_text") and state.get("hyde_text") != state["question"]:
        orig_vector = embed_query(state["question"])
        q_vector = [(a + b) / 2 for a, b in zip(q_vector, orig_vector)]

    # Check if user asks about a specific past year → include historical redactions
    year = _extract_year(state["question"])
    top_k = 15 if state.get("pipeline") == "advanced" else 5

    hits = dense_search(
        query_vector=q_vector,
        top_k=top_k,
        in_force_only=(year is None),
        redaction_year=year,
    )
    chunks = [{"text": h.payload.get("text", ""), **h.payload, "score": h.score}
              for h in hits if h.payload]
    return {**state, "chunks": chunks}


# ─── Node: Reranker (Advanced only) ───────────────────────────────────────────

def reranker_node(state: GraphState) -> GraphState:
    if not state.get("chunks"):
        return {**state, "reranked": []}
    query = state.get("rephrased_query") or state["question"]
    reranked = rerank(query=query, documents=state["chunks"], top_n=5)
    return {**state, "reranked": reranked or state["chunks"][:5]}


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
        except Exception:
            pass

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

    if has_law and has_qa:
        notes.append(
            "⚖️ Среди источников есть нормы ТК/Социального кодекса РК "
            "и разъяснения Минтруда. При противоречии приоритет имеет Трудовой кодекс РК "
            "(ст. 4 ТК РК). Разъяснения Минтруда — авторитетное толкование, но не НПА."
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

    return {**state, "conflict_note": "\n\n".join(notes)}


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

def build_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    # Group by source priority order
    priority = [
        "labor_code", "social_code", "koap", "civil_code",
        "sc_decree", "law", "government_decree", "ministerial_order",
        "labor_code_commentary", "mintrud_dialog", "mintrud_faq", "mintrud_guidelines",
    ]
    grouped: dict[str, list[dict]] = {}
    for doc in chunks[:8]:
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
            header = f"[{label}{' | ст.' + art if art else ''}]"
            context_parts.append(f"{header}\n{ctx}")
            sources.append({
                "source_type": st,
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
                "article": doc.get("article", ""),
                "paragraph": doc.get("paragraph"),
                "url": url,
                "doc_name": doc.get("doc_name"),
            })

    return "\n\n---\n\n".join(context_parts) if context_parts else "Контекст не найден.", sources


# ─── Node: Synthesizer ────────────────────────────────────────────────────────

def synthesizer_node(state: GraphState) -> GraphState:
    docs = state.get("reranked") or state.get("chunks", [])
    context, sources = build_context(docs)

    if state.get("conflict_note"):
        context = context + "\n\n---\n\n" + state["conflict_note"]

    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=state["question"])
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


# ─── Node: Citation Guard ─────────────────────────────────────────────────────

def citation_guard_node(state: GraphState) -> GraphState:
    """Check if cited articles actually exist in retrieved context."""
    answer = state.get("answer", "")
    context = state.get("context", "")

    # Extract cited article numbers from answer
    cited_arts = set(re.findall(r"ст\.\s*(\d+[-\d]*)", answer))
    context_arts = set(re.findall(r"ст\.(\d+[-\d]*)", context))

    # Allow if no specific citations or they're supported
    valid = not cited_arts or bool(cited_arts & context_arts)
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


# ─── Node: Doc Processor ──────────────────────────────────────────────────────

_DOC_SYSTEM = "Ты — юрист по трудовому праву РК. Работаешь строго по ТК РК и НПА РК."

def doc_processor_node(state: GraphState) -> GraphState:
    doc_text = state.get("doc_text", "")
    cls = state["classification"]

    if cls == "doc_generate":
        prompt = (
            f"Создай трудовой документ по следующим параметрам в соответствии с ТК РК:\n"
            f"{state['question']}\n\n"
            f"Включи все обязательные реквизиты и условия согласно ТК РК. "
            f"Оформи как готовый документ с разметкой разделов."
        )
        response = get_llm().invoke([
            {"role": "system", "content": _DOC_SYSTEM},
            {"role": "user", "content": prompt},
        ])
        return {**state, "answer": response.content, "sources": []}

    if cls == "doc_analysis" and not doc_text:
        return {
            **state,
            "answer": "Для анализа документа прикрепите его текст.",
            "sources": [],
        }

    if not doc_text:
        return {
            **state,
            "answer": "Для проверки документа прикрепите его текст.",
            "sources": [],
        }

    if cls == "doc_check":
        prompt = (
            f"Проверь документ на соответствие ТК РК.\n\n"
            f"Текст документа:\n{doc_text[:4000]}\n\n"
            f"Укажи:\n"
            f"1. Нарушения и несоответствия ТК РК (со ссылками на статьи)\n"
            f"2. Условия, ущемляющие права работника\n"
            f"3. Рекомендации по исправлению"
        )
    else:  # doc_fix
        prompt = (
            f"Исправь документ в соответствии с ТК РК.\n\n"
            f"Текст документа:\n{doc_text[:4000]}\n\n"
            f"Верни исправленный вариант с пояснениями что и почему изменено."
        )
    response = get_llm().invoke([
        {"role": "system", "content": _DOC_SYSTEM},
        {"role": "user", "content": prompt},
    ])
    return {**state, "answer": response.content, "sources": []}


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

    cls = state["classification"]
    template = _APPEAL_TEMPLATES.get(cls, _APPEAL_TEMPLATES["appeal_court"])
    prompt = template.format(context=context, question=state["question"])

    response = get_llm().invoke([
        {"role": "system", "content": _DOC_SYSTEM},
        {"role": "user", "content": prompt},
    ])
    return {
        **state,
        "answer": response.content,
        "sources": sources,
        "context": context,
    }


# ─── Node: Doc Analysis ───────────────────────────────────────────────────────

def doc_analysis_node(state: GraphState) -> GraphState:
    """Analyze an attached document with legal context from Qdrant."""
    doc_text = state.get("doc_text", "")
    docs = state.get("reranked") or state.get("chunks", [])
    context, sources = build_context(docs)

    prompt = (
        f"Проанализируй прикреплённый документ с точки зрения трудового права РК.\n\n"
        f"ТЕКСТ ДОКУМЕНТА:\n{doc_text[:4000]}\n\n"
        f"ПРИМЕНИМЫЕ НОРМЫ ТК РК:\n{context}\n\n"
        f"Дай анализ по следующим пунктам:\n"
        f"1. ЧТО ЭТО ЗА ДОКУМЕНТ — тип, правовая природа, стороны\n"
        f"2. ПРАВА И ОБЯЗАННОСТИ СТОРОН — что вытекает из документа\n"
        f"3. СООТВЕТСТВИЕ ТК РК — нарушения или несоответствия (со ссылками на статьи)\n"
        f"4. НА ЧТО ОБРАТИТЬ ВНИМАНИЕ — риски, скрытые условия, красные флаги\n"
        f"5. РЕКОМЕНДАЦИИ — что можно сделать"
    )
    response = get_llm().invoke([
        {"role": "system", "content": _DOC_SYSTEM},
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
    if cls == "doc_analysis":
        return "doc_analysis"
    return "conflict_resolver"


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("classifier", classifier_node)
    g.add_node("rephraser", rephraser_node)
    g.add_node("retriever", retriever_node)
    g.add_node("reranker", reranker_node)
    g.add_node("conflict_resolver", conflict_resolver_node)
    g.add_node("synthesizer", synthesizer_node)
    g.add_node("citation_guard", citation_guard_node)
    g.add_node("out_of_scope", out_of_scope_node)
    g.add_node("doc_processor", doc_processor_node)
    g.add_node("appeal", appeal_node)
    g.add_node("doc_analysis", doc_analysis_node)

    g.set_entry_point("classifier")

    g.add_conditional_edges("classifier", route_after_classifier, {
        "rephraser": "rephraser",
        "retriever": "retriever",
        "out_of_scope": "out_of_scope",
        "doc_processor": "doc_processor",
    })

    g.add_edge("rephraser", "retriever")
    g.add_edge("retriever", "reranker")

    g.add_conditional_edges("reranker", route_after_reranker, {
        "conflict_resolver": "conflict_resolver",
        "appeal": "appeal",
        "doc_analysis": "doc_analysis",
    })

    g.add_edge("conflict_resolver", "synthesizer")
    g.add_edge("synthesizer", "citation_guard")

    g.add_conditional_edges("citation_guard", route_after_citation_guard, {
        "synthesizer": "synthesizer",
        END: END,
    })

    g.add_edge("out_of_scope", END)
    g.add_edge("doc_processor", END)
    g.add_edge("appeal", END)
    g.add_edge("doc_analysis", END)

    return g.compile()


# Singleton compiled graph
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


@traceable(name="langgraph_qa")
def run_graph(question: str, pipeline: str = "advanced", doc_text: str = "") -> dict:
    graph = get_graph()
    initial_state: GraphState = {
        "question": question,
        "pipeline": pipeline,
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
        "doc_text": doc_text,
        "doc_clauses": [],
        "conflict_note": "",
        "error": "",
    }
    final = graph.invoke(initial_state)
    return {
        "answer": final.get("answer", ""),
        "sources": final.get("sources", []),
        "classification": final.get("classification", ""),
        "pipeline": pipeline,
    }
