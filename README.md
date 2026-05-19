# Enbek AI — AI-ассистент по трудовому праву РК

Интеллектуальный ассистент для HR-специалистов, юристов МСБ и работников Казахстана. Отвечает на вопросы по Трудовому кодексу РК со ссылками на источники, проверяет и генерирует трудовые документы.

## Возможности

- **Q&A по трудовому праву** — ответы на основе ТК РК, Социального кодекса, НП ВС РК и разъяснений Минтруда с dialog.egov.kz
- **Проверка документов** — анализ трудовых договоров на соответствие ТК РК
- **Генерация договоров** — создание трудовых договоров по параметрам
- **Локальная защита ПДн** — MCP-сервер маскирует ИИН, ФИО, телефоны до отправки в LLM

## Стек

| Компонент | Технология |
|---|---|
| LLM primary | GPT-4.1 (OpenAI free tier, 1M tok/day) |
| LLM mini | GPT-4.1-mini (классификация, HyDE, judge) |
| Fallback | Gemini 2.5 Pro |
| Embeddings | text-embedding-3-small (1536 dim) |
| Reranker | Cohere Rerank 3.5 API |
| Vector DB | Qdrant Cloud (hybrid dense+sparse) |
| Auth + DB | Supabase (email auth, RLS, queries_log) |
| Orchestration | LangGraph (9 nodes, 3 branches, citation loop) |
| Tracing | LangSmith |
| Backend | FastAPI |
| Frontend stub | Streamlit |
| MCP | Python mcp SDK (FastMCP, 3 tools) |
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

## Источники данных (5555 чанков в Qdrant)

| # | Источник | Чанков | Вес |
|---|---|---|---|
| 1 | Трудовой кодекс РК (ст.1-250) | 1825 | 1.0 |
| 2 | Социальный кодекс РК | 3045 | 0.95 |
| 3 | КоАП РК (трудовые статьи) | 188 | 0.90 |
| 4 | НП ВС РК № 9 о трудовых спорах | 151 | 0.85 |
| 5 | Правила исчисления средней зарплаты | 9 | 0.80 |
| 6 | Q&A Минтруда (dialog.egov.kz) | 337 | 0.60 |

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

Подробнее: [ARCHITECTURE.md](ARCHITECTURE.md) | Метрики: [EVALS.md](EVALS.md)

## Структура проекта

```
enbek-ai/
├── apps/api/            # FastAPI backend
├── apps/stub_ui/        # Streamlit UI
├── apps/mcp_server/     # MCP (mask_pii, unmask, validate_iin)
├── packages/rag/        # Basic + Advanced RAG pipelines
├── packages/evals/      # Eval runner + metrics
├── skills/              # kz-legal-citation-formatter SKILL.md
├── data/golden/         # 32 golden Q&A examples
├── scripts/             # ingest.py, run_evals.py
└── supabase/migrations/ # SQL schema + RLS
```
