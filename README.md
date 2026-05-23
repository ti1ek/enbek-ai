# Enbek AI — AI-ассистент по трудовому праву РК

Интеллектуальный ассистент для HR-специалистов, юристов МСБ и работников Казахстана. Отвечает на вопросы по Трудовому кодексу РК со ссылками на источники.

## Возможности

- **Q&A по трудовому праву** — ответы на основе ТК РК, Социального кодекса, НП ВС РК и разъяснений Минтруда с dialog.egov.kz
- **Локальная защита ПДн** — MCP-сервер маскирует ИИН, ФИО, телефоны до отправки в LLM

## Стек

| Компонент | Технология |
|---|---|
| LLM primary | GPT-4.1 (OpenAI), fallback Gemini 2.5 Flash |
| LLM mini | GPT-4.1-mini (классификация, HyDE, judge), fallback Gemini 2.5 Flash |
| Embeddings | text-embedding-3-small (1536 dim, OpenAI) |
| Reranker | Cohere Rerank 3.5 API |
| Vector DB | Qdrant Cloud (hybrid dense+sparse BM25) |
| Orchestration | LangGraph (9 nodes, 3 branches, citation loop) |
| Tracing | LangSmith |
| Backend | FastAPI |
| Frontend stub | Streamlit |
| MCP | Python mcp SDK (FastMCP, 2 tools) |
| Doc parsing | LlamaParse (PDF/DOCX/OCR) |

## Быстрый старт

### Docker (рекомендуется)

```bash
git clone https://github.com/ti1ek/enbek-ai
cd enbek-ai
cp .env.example .env   # заполнить ключи
docker compose up --build
# FastAPI: http://localhost:8000
# Streamlit: http://localhost:8501
```

### Нативный Python

```bash
uv sync
cp .env.example .env   # заполнить ключи
uv run python scripts/ingest.py          # ~5 мин (однократно)
uvicorn apps.api.main:app --port 8000 &
streamlit run apps/stub_ui/app.py --server.port 8501
```

### Запуск MCP-сервера

```bash
uv run python apps/mcp_server/server.py
```

Подключение в Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "enbek-pii-guard": {
      "command": "uv",
      "args": ["run", "python", "apps/mcp_server/server.py"],
      "cwd": "/absolute/path/to/enbek-ai"
    }
  }
}
```

### Эвалюации

```bash
uv run python scripts/run_evals.py --pipeline advanced
uv run python scripts/run_evals.py --pipeline both   # A/B: advanced vs basic
```

## Источники данных (26 237 точек в Qdrant)

| # | Источник | Чанков |
|---|---|---|
| 1 | Трудовой кодекс РК — текущая редакция | ~2 000 |
| 2 | Социальный кодекс РК | ~1 500 |
| 3 | КоАП РК (трудовые статьи, whitelist) | ~200 |
| 4 | НП ВС РК о трудовых спорах (НП ВС №1/2024) | ~150 |
| 5 | Правила исчисления средней зарплаты (ПП РК) | ~10 |
| 6 | Исторические редакции ТК РК (2020–2025) | ~14 578 |
| 7 | Q&A Минтруда (dialog.egov.kz) | 5 636 |
| 8 | Нормативы МРП/МЗП/ПМ (2024–2026) | 12 |
| 9 | Методические рекомендации Минтруда (gov.kz) | 191 |
| 10 | Комментарий к ТК РК (tkrk.kz) | 388 |

## Архитектура LangGraph

```
Запрос → [Classifier] → qa / doc_* / out_of_scope
                 │
         qa ────►[Rephraser/HyDE] → [Retriever/Qdrant] → [Reranker/Cohere]
                                                                   │
                                                       [Synthesizer/GPT-4.1]
                                                                   │
                                                          [Citation Guard] ←─┐
                                                                   │         │ loop ≤3
                                                                   └─────────┘
```

Метрики: [EVALS.md](packages/evals/EVALS.md)

## Структура проекта

```
enbek-ai/
├── apps/api/            # FastAPI backend
├── apps/stub_ui/        # Streamlit UI
├── apps/mcp_server/     # MCP (mask_pii, validate_kz_iin)
├── packages/rag/        # Basic + Advanced RAG pipelines
├── packages/evals/      # Eval runner + metrics
├── skills/              # kz-legal-citation-formatter SKILL.md
├── data/chunks/         # scraped JSON chunks (ingested into Qdrant)
├── data/golden/         # 100 golden Q&A examples
└── scripts/             # ingest.py, run_evals.py, check_updates.py
```
