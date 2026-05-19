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
from packages.rag.annual_norms import is_salary_related, get_norms_context

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
    norms_context: str               # annual norms (МРП/МЗП/ПМ) if salary-related
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

def classifier_node(state: GraphState) -> GraphState:
    """Classify the question into QA or doc category."""
    prompt = f"""Классифицируй запрос пользователя по одной из категорий:
- "qa" — вопрос о трудовом законодательстве РК
- "doc_check" — проверка документа на соответствие ТК РК
- "doc_fix" — исправление/улучшение документа
- "doc_generate" — создание нового трудового документа
- "out_of_scope" — вопрос не связан с трудовым правом РК

Запрос: "{state['question']}"

Ответь ТОЛЬКО одним словом из списка: qa, doc_check, doc_fix, doc_generate, out_of_scope"""

    response = get_llm_mini().invoke(prompt)
    cls = response.content.strip().lower()
    if cls not in {"qa", "doc_check", "doc_fix", "doc_generate", "out_of_scope"}:
        cls = "qa"
    return {**state, "classification": cls}


def route_after_classifier(state: GraphState) -> str:
    cls = state["classification"]
    if cls == "qa":
        return "rephraser" if state.get("pipeline") == "advanced" else "retriever"
    elif cls == "out_of_scope":
        return "out_of_scope"
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

    # Inject annual norms if question involves salary/calculations
    norms_ctx = get_norms_context() if is_salary_related(state["question"]) else ""

    return {**state, "chunks": chunks, "norms_context": norms_ctx}


# ─── Node: Reranker (Advanced only) ───────────────────────────────────────────

def reranker_node(state: GraphState) -> GraphState:
    if not state.get("chunks"):
        return {**state, "reranked": []}
    query = state.get("rephrased_query") or state["question"]
    reranked = rerank(query=query, documents=state["chunks"], top_n=5)
    return {**state, "reranked": reranked or state["chunks"][:5]}


# ─── Node: Conflict Resolver ─────────────────────────────────────────────────

# Source hierarchy: higher index = lower priority
SOURCE_PRIORITY = {
    "labor_code": 1,
    "social_code": 2,
    "koap": 3,
    "sc_decree": 4,
    "government_decree": 5,
    "mintrud_dialog": 6,
}


def conflict_resolver_node(state: GraphState) -> GraphState:
    """Detect conflicts between sources and annotate context with priority note."""
    docs = state.get("reranked") or state.get("chunks", [])
    if len(docs) < 2:
        return {**state, "conflict_note": ""}

    # Group by source_type
    by_source: dict[str, list[dict]] = {}
    for d in docs:
        st = d.get("source_type", "unknown")
        by_source.setdefault(st, []).append(d)

    source_types = set(by_source.keys())
    has_law = bool(source_types & {"labor_code", "social_code"})
    has_qa = "mintrud_dialog" in source_types

    note = ""
    if has_law and has_qa:
        note = (
            "⚖️ Примечание: среди источников есть нормы ТК/Социального кодекса РК "
            "и разъяснения Минтруда. При противоречии приоритет имеет Трудовой кодекс РК "
            "(ст. 4 ТК РК). Разъяснения Минтруда — авторитетное толкование, но не НПА."
        )

    return {**state, "conflict_note": note}


# ─── Node: Build Context ──────────────────────────────────────────────────────

def build_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    context_parts = []
    sources = []
    for doc in chunks[:5]:
        ctx = doc.get("parent_text") or doc.get("text", "")
        context_parts.append(
            f"[{doc.get('source_type','')} | ст.{doc.get('article','')}]\n{ctx}"
        )
        sources.append({
            "source_type": doc.get("source_type"),
            "article": doc.get("article"),
            "paragraph": doc.get("paragraph"),
            "url": doc.get("url"),
            "score": doc.get("rerank_score") or doc.get("score", 0.0),
        })
    return "\n\n---\n\n".join(context_parts) if context_parts else "Контекст не найден.", sources


# ─── Node: Synthesizer ────────────────────────────────────────────────────────

def synthesizer_node(state: GraphState) -> GraphState:
    docs = state.get("reranked") or state.get("chunks", [])
    context, sources = build_context(docs)

    # Append annual norms and conflict note to context if present
    extra_parts = []
    if state.get("norms_context"):
        extra_parts.append(state["norms_context"])
    if state.get("conflict_note"):
        extra_parts.append(state["conflict_note"])
    if extra_parts:
        context = context + "\n\n---\n\n" + "\n\n".join(extra_parts)

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

def doc_processor_node(state: GraphState) -> GraphState:
    """Simple doc processing placeholder — full impl in packages/agents/."""
    doc_text = state.get("doc_text", "")
    cls = state["classification"]

    if cls == "doc_generate":
        prompt = f"""Создай трудовой договор по следующим параметрам в соответствии с ТК РК:
{state['question']}

Договор должен содержать все обязательные условия согласно ст. 28 ТК РК."""
        response = get_llm().invoke([
            {"role": "system", "content": "Ты — юрист по трудовому праву РК. Создавай документы строго по ТК РК."},
            {"role": "user", "content": prompt},
        ])
        return {**state, "answer": response.content, "sources": []}

    if not doc_text:
        return {
            **state,
            "answer": "Для проверки документа прикрепите его текст.",
            "sources": [],
        }

    prompt = f"""Проверь следующий документ на соответствие Трудовому кодексу РК.
Укажи: 1) нарушения, 2) применимые статьи ТК РК, 3) рекомендации по исправлению.

Текст документа:
{doc_text[:3000]}"""
    response = get_llm().invoke([
        {"role": "system", "content": "Ты — юрист по трудовому праву РК."},
        {"role": "user", "content": prompt},
    ])
    return {**state, "answer": response.content, "sources": []}


# ─── Build Graph ──────────────────────────────────────────────────────────────

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

    g.set_entry_point("classifier")

    g.add_conditional_edges("classifier", route_after_classifier, {
        "rephraser": "rephraser",
        "retriever": "retriever",
        "out_of_scope": "out_of_scope",
        "doc_processor": "doc_processor",
    })

    g.add_edge("rephraser", "retriever")
    g.add_edge("retriever", "reranker")
    g.add_edge("reranker", "conflict_resolver")
    g.add_edge("conflict_resolver", "synthesizer")
    g.add_edge("synthesizer", "citation_guard")

    g.add_conditional_edges("citation_guard", route_after_citation_guard, {
        "synthesizer": "synthesizer",
        END: END,
    })

    g.add_edge("out_of_scope", END)
    g.add_edge("doc_processor", END)

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
        "norms_context": "",
        "error": "",
    }
    final = graph.invoke(initial_state)
    return {
        "answer": final.get("answer", ""),
        "sources": final.get("sources", []),
        "classification": final.get("classification", ""),
        "pipeline": pipeline,
    }
