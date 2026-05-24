# enbek ai — AI-ассистент по трудовому праву РК

Интеллектуальный ассистент для HR-специалистов, юристов МСБ и работников Казахстана. Отвечает на вопросы по Трудовому кодексу РК со ссылками на источники.

**Веб-версия:** [enbek.ai](https://enbek.ai) — работает в браузере, без установки.  
**MCP-версия:** [`/mcp`](./mcp) — локальный сервер для Claude Desktop с защитой персональных данных.

---

## Возможности

- **Q&A по трудовому праву** — ответы на основе ТК РК, Социального кодекса, нормативных постановлений ВС РК и разъяснений Минтруда
- **Прикрепление документов** — фото / скан / PDF / DOCX трудового договора или приказа: vision-OCR (изображения) и LlamaParse (PDF/DOCX) извлекают текст и подают его в LLM как предмет анализа
- **Защита персональных данных** — MCP-сервер маскирует ФИО, ИИН, названия компаний, БИН и другие данные локально до отправки в облако

---

## Стек

| Компонент | Технология |
|---|---|
| LLM primary | GPT-4.1 (OpenAI), fallback Gemini 2.5 Flash |
| LLM mini | GPT-4.1-mini (классификация, HyDE, judge) |
| Embeddings | text-embedding-3-small (1536 dim, OpenAI) |
| Reranker | Cohere Rerank 3.5 |
| Vector DB | Qdrant Cloud (hybrid dense + sparse BM25) |
| Orchestration | LangGraph (9 nodes, 3 branches, citation loop) |
| Tracing | LangSmith |
| Backend | FastAPI |
| Frontend | Next.js 14 (App Router) + Tailwind CSS |
| MCP | Python MCP SDK (маскировка персональных данных + поиск по ТК РК) |
| Парсинг документов | LlamaParse (PDF/DOCX/OCR), PyMuPDF fallback |

---

## enbek MCP — локальная защита персональных данных

Если вы работаете с реальными трудовыми документами (договорами, приказами, персональными делами), используйте MCP-версию. Все персональные данные маскируются **на вашем компьютере** до отправки любого запроса в облако.

```
Claude Desktop → enbek MCP (локально) → Qdrant (поиск по ТК)
                      ↓
                 Ollama (маскировка персональных данных)
                      ↓
                 Claude (только маскированный текст)
```

**[Инструкция по установке →](./mcp)**

---

## Источники данных (26 237 точек в Qdrant)

| Источник | Чанков |
|---|---|
| Трудовой кодекс РК — текущая редакция | ~2 000 |
| Социальный кодекс РК | ~1 500 |
| КоАП РК (трудовые статьи) | ~200 |
| Нормативное постановление ВС РК о трудовых спорах | ~150 |
| Правила исчисления средней зарплаты | ~10 |
| Исторические редакции ТК РК (2020–2025) | ~14 578 |
| Q&A Минтруда (dialog.egov.kz) | 5 636 |
| Нормативы МРП / МЗП / ПМ (2024–2026) | 12 |
| Методические рекомендации Минтруда | 191 |
| Комментарий к ТК РК | 388 |

---

## Архитектура RAG

```
Запрос → [Classifier] → qa / doc_analysis / out_of_scope
               │
        qa ───►[Rephraser / HyDE] → [Retriever / Qdrant] → [Reranker / Cohere]
                                                                     │
                                                         [Synthesizer / GPT-4.1]
                                                                     │
                                                            [Citation Guard] ←─┐
                                                                     │         │ loop ≤3
                                                                     └─────────┘
```

---

## Структура проекта

```
enbek-ai/
├── apps/
│   ├── api/         # FastAPI backend
│   ├── web/         # Next.js frontend (продакшн)
│   └── stub_ui/     # Streamlit (локальное тестирование)
├── mcp/             # MCP-сервер с защитой персональных данных
├── packages/
│   ├── rag/         # Basic + Advanced RAG pipelines
│   └── evals/       # Eval runner + метрики
├── data/
│   ├── chunks/      # JSON чанки (ingested в Qdrant)
│   └── golden/      # 100 golden Q&A для эвалуаций
└── scripts/         # ingest.py, run_evals.py, check_updates.py
```

---

## Быстрый старт (разработка)

```bash
git clone https://github.com/ti1ek/enbek-ai
cd enbek-ai
cp .env.example .env   # заполнить ключи
uv sync
uvicorn apps.api.main:app --port 8000
```

Веб-фронтенд:
```bash
cd apps/web
npm install && npm run dev   # http://localhost:3000
```

---

## Лицензия

MIT
