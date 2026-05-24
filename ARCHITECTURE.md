# ARCHITECTURE — Enbek AI

## Обзор системы

Enbek AI — многоуровневая RAG-система для консультаций по трудовому законодательству РК. Система состоит из трёх независимых слоёв: **инgest-пайплайн** (офлайн), **API-бэкенд** (онлайн) и **MCP-сервер** (локальный).

---

## Архитектурная диаграмма

```
┌─────────────────────────────────────────────────────────────────────┐
│                          ПОЛЬЗОВАТЕЛЬ                               │
│                 (HR-специалист / юрист / работник)                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  HTTP / WebSocket
            ┌──────────────▼──────────────┐
            │      Next.js 14 Frontend    │
            │      apps/web/              │
            └──────────────┬──────────────┘
                           │  POST /api/v1/ask
            ┌──────────────▼──────────────┐
            │      FastAPI Backend        │
            │      apps/api/main.py       │
            └──────────────┬──────────────┘
                           │
            ┌──────────────▼──────────────────────────────────┐
            │              LangGraph State Machine             │
            │              apps/api/graph.py                   │
            │                                                  │
            │  ┌────────────┐                                  │
            │  │ classifier │──► out_of_scope ──► END          │
            │  └─────┬──────┘                                  │
            │        │                                         │
            │   ┌────┴─────┐                                   │
            │   │ qa-ветка  │  appeal-ветка                    │
            │   └────┬─────┘                                   │
            │        ▼                                         │
            │  ┌───────────────┐                               │
            │  │ rephraser/HyDE│  (ENABLE_HYDE)                │
            │  └──────┬────────┘                               │
            │         ▼                                        │
            │  ┌───────────────┐                               │
            │  │   retriever   │◄── Qdrant hybrid RRF          │
            │  │   (3-hop)     │    dense 1536 + BM25 sparse   │
            │  └──────┬────────┘                               │
            │         ▼                                        │
            │  ┌───────────────┐                               │
            │  │   reranker    │◄── Cohere rerank-v3.5         │
            │  │ (ENABLE_RERANK│                               │
            │  └──────┬────────┘                               │
            │         ▼                                        │
            │  ┌──────────────────┐                            │
            │  │ conflict_resolver│  Кодекс > ПП > Приказ      │
            │  └──────┬───────────┘  > НП ВС > Минтруд        │
            │         ▼                                        │
            │  ┌───────────────┐                               │
            │  │  synthesizer  │◄── gpt-4.1-mini temp=0.1      │
            │  └──────┬────────┘                               │
            │         ▼                                        │
            │  ┌───────────────┐                               │
            │  │   verifier    │  (ENABLE_VERIFIER)            │
            │  └──────┬────────┘  Self-RAG critique            │
            │         ▼                                        │
            │  ┌──────────────────────┐                        │
            │  │ citation_guard       │◄── loop ≤ 3            │
            │  │ _strip_ungrounded_   │    _linkify_plain_      │
            │  │ urls()               │    citations()          │
            │  └──────┬───────────────┘                        │
            │         ▼                                        │
            │        END                                        │
            └──────────────────────────────────────────────────┘
                           │
            ┌──────────────▼──────────────┐
            │         LangSmith           │
            │   трейсинг всех LLM-вызовов │
            └─────────────────────────────┘
```

---

## 3-Hop Retrieval Detail

```
hop1: hybrid search (codex + laws)
  query: исходный (или HyDE-расширенный) вопрос
  filter: source_type IN [kodex, zakon]
  top_k: 20
  └──► результаты hop1

hop2: targeted search (orders + decrees + НП ВС)
  query: gpt-4.1-mini планирует 1-3 точечных подзапроса по hop1
  filter: source_type IN [prikaz, postanovlenie, np_vs]
  top_k: 15
  └──► результаты hop2

hop3: Q&A confirmation (MinTrud answers)
  query: исходный вопрос
  filter: source_type IN [mintrud_dialog, mintrud_faq]
  top_k: 10
  └──► результаты hop3

merge: deduplicate by chunk_id → rerank → top-25 → synthesizer
```

---

## Ingest Pipeline (офлайн)

```
adilet.zan.kz          dialog.egov.kz       tkrk.kz / gov.kz
     │                       │                    │
     ▼                       ▼                    ▼
scrape_adilet.py    scrape_dialog_egov.py   scrape_tkrk.py
scrape_adilet_history.py                scrape_govkz_methodology.py
     │                       │                    │
     └───────────────────────┴────────────────────┘
                             │
                             ▼
                    parent-child chunking
                    (text ≤ 4000 / parent_text ≤ 8000)
                             │
                             ▼
                    metadata.enrich()          ← детерминированное
                    metadata.tag_topics_llm()  ← gpt-4.1-mini
                             │
                             ▼
                    embeddings.embed_batch()   ← text-embedding-3-small
                    (batch 100, MAX_CHARS 6000)
                             │
                             ▼
                    qdrant.upsert()            ← коллекция kz_legal
                    dense 1536 + sparse BM25
```

---

## MCP Server (локальный, автономный)

```
Claude Desktop / Claude Code / Cursor / Windsurf
     │
     │  MCP protocol (stdio)
     ▼
mcp/tools.py
  ├── mask_pii(text)         → Ollama llama3.2:3b (локально)
  ├── retrieve(query)        → Qdrant Cloud
  └── search_labor_code(q)   → mask_pii + retrieve
```

Персональные данные никогда не покидают локальную машину.

---

## Стек технологий

| Компонент | Технология | Причина выбора |
|---|---|---|
| Оркестрация | LangGraph | Условный роутинг, циклы, явный граф состояния |
| LLM primary | gpt-4.1-mini | Стоимость/качество на кириллице, temp 0.1 синтез |
| LLM fallback | gemini-2.5-flash | OpenAI-compatible endpoint, отказоустойчивость |
| Embeddings | text-embedding-3-small 1536d | Кириллица, $0.02/M токен, нет fallback |
| Vector DB | Qdrant Cloud | Нативный RRF, sparse IDF Modifier |
| Reranker | Cohere rerank-v3.5 | Мультиязычный cross-encoder |
| API | FastAPI + uvicorn | async-first, pydantic, OpenAPI |
| Frontend | Next.js 14 | SSR/SEO, streaming |
| Трейсинг | LangSmith | Нативная интеграция с LangGraph |
| MCP runtime | Ollama llama3.2:3b | Локальная PII-маскировка |
| Контейнер | Docker + Compose | Одна команда запуска |

---

## Независимые компоненты (заменяемые)

| Компонент | Что можно заменить | Trade-off |
|---|---|---|
| `gpt-4.1-mini` | Любая OpenAI-compatible модель | Качество vs стоимость |
| `text-embedding-3-small` | Другая модель той же размерности | Требует полного re-ingest |
| Cohere rerank | Любой reranker API | Ablation показал нейтральность на нашем датасете |
| Qdrant | Pinecone/Weaviate (без RRF из коробки) | Потребует custom fusion |
| `llama3.2:3b` | Любая Ollama-совместимая модель | Качество PII-маскировки |

---

## Feature Flags

```python
ENABLE_HYBRID = True        # dense + sparse RRF — критично
ENABLE_HYDE = True          # HyDE query expansion — ablation: +шум
ENABLE_RERANK = True        # Cohere reranking — ablation: нейтрально
ENABLE_VERIFIER = True      # Self-RAG critique — улучшает faithfulness
ENABLE_DECOMPOSE = False    # Query decomposition — не тестировалось
ENABLE_GRAPH_EXPAND = False # Cross-doc graph — РЕГРЕССИРУЕТ в evals
STRICT_CITATION_GUARD = True
```

**Продакшн-рекомендация:** `ENABLE_HYDE=false ENABLE_RERANK=false` (no_hyde_rerank конфигурация, faithfulness 0.703).

---

## Поток одного запроса

1. Пользователь вводит вопрос в браузере → `POST /api/v1/ask`
2. `classifier` (gpt-4.1-mini, temp=0) → `qa` / `appeal` / `out_of_scope`
3. `rephraser` генерирует HyDE-документ + синонимы
4. `retriever`: hop1 кодексы → hop2 подзаконные акты → hop3 Минтруд Q&A
5. `reranker`: Cohere cross-encoder сортирует top-50 → top-25
6. `conflict_resolver`: применяет иерархию источников по ст. 4 ТК РК
7. `synthesizer` (gpt-4.1-mini, temp=0.1): генерирует ответ со ссылками
8. `verifier` проверяет: каждое утверждение в ответе есть в источниках?
9. `citation_guard`: удаляет неверные URL, linkify статьи/Минтруд/НП ВС
10. Ответ с кликабельными ссылками → пользователь
