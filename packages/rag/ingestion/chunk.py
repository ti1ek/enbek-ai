"""Parent-child chunking for KZ legal documents.

Child = paragraph (пункт) — embedded and searched.
Parent = full article (статья) — fed to LLM for synthesis.
"""
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_id: str          # unique: doc_id_article_paragraph
    parent_id: str         # doc_id_article (full article text)
    text: str              # child text (paragraph)
    parent_text: str       # full article text (for LLM context)
    source_type: str
    doc_id: str
    article: str
    paragraph: str
    redaction_date: str
    in_force: bool
    url: str
    hierarchy_weight: float = 1.0
    extra: dict = field(default_factory=dict)


def chunk_article(
    doc_id: str,
    source_type: str,
    article_num: str,
    article_title: str,
    paragraphs: list[str],
    redaction_date: str,
    in_force: bool,
    base_url: str,
    hierarchy_weight: float = 1.0,
) -> list[Chunk]:
    """Splits one article into parent-child chunks."""
    parent_text = f"Статья {article_num}. {article_title}\n\n" + "\n".join(paragraphs)
    parent_id = f"{doc_id}_{article_num}"

    chunks = []
    for i, para in enumerate(paragraphs, 1):
        if not para.strip():
            continue
        chunk_id = f"{parent_id}_{i}"
        chunks.append(Chunk(
            chunk_id=chunk_id,
            parent_id=parent_id,
            text=para.strip(),
            parent_text=parent_text,
            source_type=source_type,
            doc_id=doc_id,
            article=article_num,
            paragraph=str(i),
            redaction_date=redaction_date,
            in_force=in_force,
            url=f"{base_url}#z{article_num}",
            hierarchy_weight=hierarchy_weight,
        ))
    return chunks


def chunk_qa_pair(
    doc_id: str,
    source_type: str,
    question: str,
    answer: str,
    category: str = "",
    url: str = "",
) -> Chunk:
    """One Q&A pair = one atomic chunk (no parent-child needed)."""
    text = f"Вопрос: {question}\nОтвет: {answer}"
    chunk_id = f"{doc_id}_{abs(hash(question)) % 10**8}"
    return Chunk(
        chunk_id=chunk_id,
        parent_id=chunk_id,
        text=text,
        parent_text=text,
        source_type=source_type,
        doc_id=doc_id,
        article=category,
        paragraph="",
        redaction_date="",
        in_force=True,
        url=url,
        hierarchy_weight=0.5,
        extra={"question": question, "answer": answer},
    )
