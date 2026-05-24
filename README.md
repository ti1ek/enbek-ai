# Enbek AI — Labour Law Assistant for Kazakhstan

> **Production-grade RAG system** for Kazakhstan Labour Code (ТК РК) and related legislation.  
> Answers HR managers, SMB owners, and workers in Russian/Kazakh with verified, cited legal answers.

| Layer | Technology |
|---|---|
| Orchestration | LangGraph 9-node state machine |
| LLM (primary / fallback) | `gpt-4.1-mini` / `gemini-2.5-flash` |
| Embeddings | `text-embedding-3-small` · 1536 dims · OpenAI |
| Vector DB | Qdrant Cloud · hybrid dense+sparse RRF |
| Reranker | Cohere `rerank-v3.5` |
| Evaluation | RAGAS 0.2.6 · 25 golden Q&A · 7 ablation runs |
| API | FastAPI · uvicorn |
| Web | Next.js 14 |
| Local MCP | Ollama `llama3.2:3b` · PII masking |

↓ Полная документация на русском

---

## Содержание

1. [Что это](#1-что-это)
2. [Сбор данных](#2-сбор-данных)
3. [Стратегия чанкинга](#3-стратегия-чанкинга-parent-child--small-to-big)
4. [Обогащение метаданных](#4-обогащение-метаданных)
5. [Индекс Qdrant — гибридный поиск](#5-индекс-qdrant--гибридный-поиск)
6. [Golden dataset — 25 эталонных пар](#6-golden-dataset--25-эталонных-пар)
7. [Архитектура RAG (LangGraph, 9 узлов)](#7-архитектура-rag-langgraph-9-узлов)
8. [Мультимодальность](#8-мультимодальность)
9. [Эвалуация](#9-эвалуация)
10. [Обоснование инженерных выборов](#10-обоснование-инженерных-выборов)
11. [Структура проекта](#11-структура-проекта)
12. [MCP — локальная защита ПДн](#12-mcp--локальная-защита-пдн)
13. [Быстрый старт](#13-быстрый-старт)
14. [Чеклист соответствия заданию](#14-чеклист-соответствия-заданию)

---

## 1. Что это

**Enbek AI** — RAG-система для консультаций по трудовому законодательству РК. Система предоставляет юридически обоснованные ответы со ссылками на конкретные статьи законодательных актов и их официальные редакции на портале adilet.zan.kz.

**Аудитория:** HR-специалисты, юристы малого и среднего бизнеса, работники РК.

**Два режима доступа:**
- **Web-интерфейс** — полноценный диалоговый интерфейс ([enbek.ai](https://enbek.ai)) на базе Next.js + FastAPI
- **MCP-инструменты** — локальная интеграция в Claude Desktop / Cursor / Windsurf с маскировкой ПДн через Ollama (см. `./mcp`)

---

## 2. Сбор данных

### Источники

Данные собраны из официальных государственных порталов: [adilet.zan.kz](https://adilet.zan.kz), [dialog.egov.kz](https://dialog.egov.kz), [tkrk.kz](https://tkrk.kz), [gov.kz](https://gov.kz).

| Источник | Тип | Описание |
|---|---|---|
| ТК РК `K1500000414` | Кодекс | Трудовой кодекс, все редакции 2020–2025 |
| Социальный кодекс `K2300000224` | Кодекс | Нормы об обязательном соцстраховании |
| КоАП (ст. 86–99, 414–420) | Кодекс | Административная ответственность за нарушения |
| ГК РК, гл. 47 | Кодекс | Договор возмездного оказания услуг |
| НП ВС РК `P240000001S` | Нормативное постановление | Постановление Верховного Суда №1 от 28.11.2024 о трудовых спорах |
| 5 профильных законов | Закон | Об охране труда, о коллективных договорах, о занятости, о профсоюзах, о медиации |
| 3 постановления правительства | ПП | Об утверждении типовых правил |
| 13 приказов Минтруда | Приказ | Методики расчёта, нормы охраны труда |
| dialog.egov.kz Q&A | Разъяснения Минтруда | Официальные ответы Министерства труда на вопросы граждан |
| Исторические редакции | Архив | Редакции ТК РК 2020–2025 для апелляционных вопросов |
| Комментарий к ТК | Методология | tkrk.kz / gov.kz методологические разъяснения |

### Метод сбора (`packages/rag/ingestion/`)

Реализован набор async-скраперов (`scrape_adilet.py`, `scrape_dialog_egov.py`, `scrape_adilet_history.py`, `scrape_tkrk.py`, `scrape_govkz_methodology.py`):

- **HTTP**: `httpx` async с `verify=False` для adilet.zan.kz (портал использует самоподписанный сертификат)
- **Парсинг**: `selectolax` для извлечения HTML, regex по якорям `<a name="zN">Статья M` для разбивки на статьи
- **Rate limit**: 1.5 сек между запросами
- **Идемпотентность**: `content_hash` (SHA256[:16]) предотвращает повторную обработку неизменённых документов

---

## 3. Стратегия чанкинга (Parent-Child / Small-to-Big)

Реализована в `scrape_adilet.py:219–404` и `ingest.py:96–107`.

### Логика разбивки

```
Статья < 4 000 симв  →  каждый параграф = отдельный child-чанк
Статья > 4 000 симв  →  блоки ~2 000 симв (_group_paragraphs_into_blocks)
```

Каждый чанк содержит два поля:
- `text` — child (параграф или блок), **используется для эмбеддинга и similarity search**
- `parent_text` — полный текст статьи, **передаётся LLM для синтеза ответа**

Ограничения payload: `parent_text` ≤ 8 000 симв, `text` ≤ 4 000 симв — под лимиты Qdrant.

### Почему именно такой подход

Мелкий child-чанк даёт **точный semantic match** при поиске (параграф ближе к конкретному вопросу), а полный текст статьи в `parent_text` обеспечивает **полный контекст** для LLM при синтезе: модель видит условия применения нормы, исключения и смежные пункты той же статьи.

Альтернатива — fixed-size chunking (512 / 1024 токен) — неприемлема для юридического текста: она разрезает нормы посередине предложения, уничтожая семантику. В наших ablation-экспериментах baseline уже использует parent-child; переход на fixed-size не тестировался ввиду явной деградации качества на структурированных правовых текстах.

### Идентификаторы

- `chunk_id = uuid5(DNS, "{doc_id}_{article}_{seq}")` — детерминированный, upsert-идемпотентный
- `content_hash` — первые 16 символов SHA256 от `text + parent_text`; используется для пропуска неизменённых статей при повторном ingest

---

## 4. Обогащение метаданных

Реализовано в `packages/rag/ingestion/metadata.py`.

### Детерминированное обогащение (`enrich()`)

Без LLM-вызовов, на основе regex и словарей:
- `doc_type`: `kodex` / `zakon` / `postanovlenie` / `prikaz` / `np_vs` / `mintrud_dialog`
- `year`: извлекается из даты редакции или названия документа
- `chunk_type`: `article` / `paragraph` / `block`
- `in_force`: `true/false` по дате вступления в силу

### LLM topic-tagging (`tag_topics_llm()`)

- Модель: `gpt-4.1-mini`, температура 0
- Таксономия из 20 тем (увольнение, оплата труда, охрана труда, отпуска, трудовые споры и т.д.)
- Батчинг: 20 чанков за вызов, concurrency 8
- Фильтр галлюцинаций: whitelist тем — любой тег вне таксономии отбрасывается
- Используется для payload-фильтрации при retrieval (narrowing по теме запроса)

---

## 5. Индекс Qdrant — гибридный поиск

Реализовано в `packages/rag/qdrant_client.py`.

### Конфигурация коллекции `kz_legal`

| Параметр | Значение |
|---|---|
| Dense vector | 1536 dims, COSINE distance |
| Sparse vector | BM25 с `Modifier.IDF` |
| Storage | `memmap_threshold` для экономии RAM |
| Payload-индексы | `source_type`, `article`, `in_force`, `year`, `doc_id`, `redaction_date` |

### Hybrid retrieval

```python
query_result = client.query_points(
    collection_name="kz_legal",
    prefetch=[
        Prefetch(query=dense_vector, using="dense", limit=50),
        Prefetch(query=sparse_vector, using="sparse", limit=50),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=top_k,
)
```

**Reciprocal Rank Fusion (RRF)** объединяет ранжирование по векторному сходству (семантический поиск) и по TF-IDF BM25 (лексическое совпадение). На юридических текстах это критично: запрос «статья 52 пункт 1 подпункт 2» должен совпасть лексически (BM25), а «незаконное увольнение беременной» — семантически (dense).

---

## 6. Golden Dataset — 25 эталонных пар

Файл: `data/golden/np_golden.jsonl`

### Состав

25 пар «вопрос / эталонный ответ» по **Нормативному постановлению Верховного Суда РК №1 от 28.11.2024** о рассмотрении трудовых споров (`P240000001S`).

Поля каждой записи:
```jsonl
{
  "id": "np_001",
  "question": "Какие сроки исковой давности по трудовым спорам?",
  "reference_answer": "...",
  "category": "трудовые_споры",
  "source_text": "...",
  "url": "https://adilet.zan.kz/rus/docs/P240000001S"
}
```

### Почему именно НП ВС РК

НП ВС РК — **единственный источник с проверяемыми эталонами** в контексте RAGAS-метрик `context_recall` и `answer_correctness`:
- Постановление содержит конкретные правовые позиции с однозначными формулировками → `reference_answer` можно верифицировать
- Документ охватывает весь спектр трудовых споров → высокая тематическая плотность на 25 вопросов
- Дата выхода (28.11.2024) гарантирует актуальность для текущей редакции ТК РК

Альтернатива — 100 вопросов по всему ТК — была отброшена: для RAGAS важно качество `reference_answer`, а не количество; вручную верифицированные 25 примеров достовернее автогенерированных 100.

---

## 7. Архитектура RAG (LangGraph, 9 узлов)

Реализовано в `apps/api/graph.py`.

### Диаграмма пайплайна

```
                    ┌─────────────┐
         вопрос ──► │ classifier  │
                    └──────┬──────┘
              ┌────────────┼─────────────┐
              ▼            ▼             ▼
         qa-ветка    appeal-ветка   out_of_scope
              │
    ┌─────────▼──────────┐
    │ rephraser / HyDE   │  (ENABLE_HYDE)
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │  retriever (3-hop) │
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │    reranker        │  (ENABLE_RERANK)
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │ conflict_resolver  │
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │   synthesizer      │
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │    verifier        │  (ENABLE_VERIFIER)
    └─────────┬──────────┘
              │
    ┌─────────▼──────────────────┐
    │ citation_guard (loop ≤ 3)  │
    └─────────┬──────────────────┘
              ▼
             END
```

### Узлы и их роль

| Узел | Функция |
|---|---|
| `classifier` | Определяет тип вопроса: `qa` / `appeal_*` / `out_of_scope` через gpt-4.1-mini |
| `rephraser / HyDE` | Генерирует гипотетический документ (HyDE) + канонические синонимы запроса; при `ENABLE_DECOMPOSE` — декомпозиция сложных вопросов |
| `retriever (3-hop)` | Трёхуровневый retrieval (см. ниже) |
| `reranker` | Cohere `rerank-v3.5` — сортировка топ-результатов |
| `conflict_resolver` | Иерархия источников: Кодекс > ПП > Приказ > НП ВС > Минтруд; при противоречии исключает Минтруд (ст. 4 ТК РК) |
| `synthesizer` | Генерирует ответ на основе отобранных источников, температура 0.1 |
| `verifier` | Self-RAG критика: проверяет grounding ответа в источниках; fail-open при ошибке |
| `citation_guard` | Постобработка: `_strip_ungrounded_urls` + `_linkify_plain_citations`; до 3 итераций при обнаружении неверных ссылок |

### 3-hop retrieval

```
hop1: кодексы + законы  →  dense+sparse hybrid, top-20
hop2: приказы / ПП / НП ВС  →  gpt-4.1-mini планирует точечные запросы по hop1-результатам
hop3: Q&A Минтруда  →  поиск практических разъяснений как подтверждение
```

Три хопа исключают слепые пятна: нормы часто раскрываются не в кодексе, а в подзаконных актах (порядок расчёта — в приказах Минтруда), и трёхуровневый поиск собирает полную правовую цепочку.

### Фича-флаги

| Флаг | По умолчанию | Описание |
|---|---|---|
| `ENABLE_HYBRID` | `true` | Hybrid dense+sparse RRF |
| `ENABLE_HYDE` | `true` | HyDE query expansion |
| `ENABLE_RERANK` | `true` | Cohere reranking |
| `ENABLE_VERIFIER` | `true` | Self-RAG verifier |
| `ENABLE_DECOMPOSE` | `false` | Query decomposition |
| `ENABLE_GRAPH_EXPAND` | `false` | Cross-doc graph expansion |
| `STRICT_CITATION_GUARD` | `true` | Строгая проверка ссылок |

### Grounding ссылок

`citation_guard` выполняет две функции постобработки:
1. `_strip_ungrounded_urls` — удаляет из ответа любые URL, которых нет в `sources`
2. `_linkify_plain_citations` — преобразует текстовые упоминания статей (`ст. 52 ТК РК`) и источников (`Разъяснение Минтруда РК`, `НП ВС РК`) в кликабельные Markdown-ссылки с round-robin по нескольким URL одного типа

---

## 8. Мультимодальность

Реализовано в `packages/multimodal.py`.

| Входной формат | Метод обработки |
|---|---|
| PDF (текстовый) | LlamaParse → структурированный текст |
| PDF (сканированный) | PyMuPDF рендер страниц в изображения → vision OCR (gpt-4.1) |
| DOCX | python-docx → plain text |
| Изображения (JPG/PNG) | Vision OCR напрямую |

LlamaParse используется как первичный инструмент для PDF/DOCX с сохранением структуры (заголовки, таблицы). Если LlamaParse недоступен — local fallback на PyMuPDF / python-docx. Для сканированных PDF: PyMuPDF рендерит каждую страницу в изображение, затем vision-модель извлекает текст. Лимит: max 8 страниц за вызов для vision OCR.

---

## 9. Эвалуация

Фреймворк: **RAGAS 0.2.6**, judge-модель: `gpt-4.1-mini`, n=25, golden set: `data/golden/np_golden.jsonl`.

Метрики: `faithfulness` (верность источникам), `answer_relevancy` (релевантность ответа), `context_precision` (точность retrieved контекста), `context_recall` (полнота recalled контекста), `answer_correctness` (соответствие эталону).

### Таблица A/B/C: три конфигурации

| Конфигурация | Faithfulness | Answer Rel. | Context Prec. | Context Recall | Answer Corr. | Latency (ms) |
|---|---|---|---|---|---|---|
| **A — Basic** (только hybrid) | **0.714** | **0.927** | 0.589 | **0.640** | **0.446** | **6 977** |
| **B — Advanced** (hybrid + HyDE + rerank + verifier) | 0.661 | 0.764 | **0.777** | 0.460 | 0.436 | 17 892 |
| **C — Graph** (Advanced + ENABLE_GRAPH_EXPAND) | 0.698 | 0.690 | 0.685 | 0.420 | 0.414 | 17 751 |

**Вывод:** Basic превосходит Advanced по faithfulness (+5.3%), answer_relevancy (+16.3%), context_recall (+18%) при втрое меньшей latency. Advanced выигрывает только по context_precision (+18.8%), что указывает на более точный отбор чанков, но за счёт меньшего охвата и большего шума в ответе.

### Ablation study: влияние компонентов на faithfulness

База сравнения: конфигурация Advanced (baseline = 0.661).

| Конфигурация | Faithfulness | Δ к baseline |
|---|---|---|
| `no_hyde_hybrid` | 0.559 | −0.102 |
| `no_hybrid` | 0.583 | −0.078 |
| `no_verifier` | 0.596 | −0.065 |
| `no_hyde` | 0.647 | −0.014 |
| `no_rerank` | 0.657 | −0.004 |
| baseline (Advanced) | 0.661 | — |
| `no_rerank_verifier` | 0.680 | +0.019 |
| **`no_hyde_rerank` ★** | **0.703** | **+0.042** |

**Интерпретация:**
- `no_hyde_rerank` (+4.2%) — лучший результат: HyDE расширяет запрос, но на узкоспецифичных правовых вопросах гипотетический документ вводит терминологический шум; reranker перераспределяет релевантность, но на данном golden set снижает faithfulness. Отключение обоих компонентов вместе даёт синергетический эффект.
- `no_hyde_hybrid` (−10.2%) — отключение HyDE при одновременном отключении hybrid — катастрофа: без расширения запроса lexical BM25 не находит нужные нормы по перефразировкам.
- `hybrid` критичен: отключение снижает faithfulness на −7.8%, что подтверждает необходимость совместного dense+sparse поиска для юридических текстов.

**Рекомендация для продакшна:** конфигурация `no_hyde_rerank` (`ENABLE_HYDE=false`, `ENABLE_RERANK=false`, `ENABLE_HYBRID=true`, `ENABLE_VERIFIER=true`).

### Эксперимент с графами (ENABLE_GRAPH_EXPAND) — почему не взлетел

**Построение графа** (`scripts/build_cross_doc_edges.py`):
1. Двухшаговый LLM-матчинг: сначала `article × document → yes/no` (связана ли статья с другим документом), затем `article × paragraphs → [список пунктов]` (какие конкретно)
2. Рёбра сохранены как `linked_chunks` в payload Qdrant
3. При `ENABLE_GRAPH_EXPAND=true`: после retrieval дополнительно загружаются все linked_chunks

**Результат:** конфигурация Graph регрессирует относительно Basic по всем метрикам (faithfulness −1.6%, context_recall −22%, answer_relevancy −25.7%).

**Причина провала:** граф добавляет _связанные_ чанки, но не _более релевантные_ к конкретному вопросу. На узкотематических вопросах НП ВС РК граф подтягивает процессуальные нормы (ГПК, ГК) из cross-doc рёбер — тематически корректных, но ответственных за снижение faithfulness: LLM видит больше источников и чаще «уходит» от вопроса. Вывод: graph expansion уместен для вопросов, явно охватывающих несколько документов, но деградирует как глобально применяемое усиление.

---

## 10. Обоснование инженерных выборов

### Фреймворк оркестрации: LangGraph vs LangChain / LlamaIndex

| | LangGraph | Голый LangChain | LlamaIndex |
|---|---|---|---|
| Условный роутинг | ✅ нативный | ручная логика | ограниченно |
| Циклы (citation loop, verifier retry) | ✅ нативный | сложно | нет |
| Явный граф состояния | ✅ | нет | нет |
| Observability (LangSmith) | ✅ нативная | ✅ | частично |

**Вывод:** пайплайн требует условного роутинга (3 ветки классификатора), цикла citation_guard (до 3 итераций) и retry-логики verifier. LangGraph — единственный из трёх, где это реализуется декларативно без ad-hoc кода.

### LLM: `gpt-4.1-mini` + Gemini fallback

- `gpt-4.1-mini` — оптимальный баланс стоимость/качество для multi-hop синтеза на кириллице; температура 0.1 для синтезатора (детерминизм) и 0 для классификатора/judge
- Fallback на `gemini-2.5-flash` через OpenAI-compatible endpoint (`generativelanguage.googleapis.com/v1beta/openai/`) — обеспечивает отказоустойчивость без изменения кода; Gemini также используется для RAGAS scoring (бюджет OpenAI зарезервирован только для продакшн-эмбеддингов)
- `gpt-4.1-mini` используется для обоих полей `llm_model` и `llm_mini_model` — разница оставлена для будущей дифференциации (например, при переходе на gpt-4.1 для сложных синтезов)

### Эмбеддинги: `text-embedding-3-small` 1536 dims

- **Нет cross-provider fallback** — вектор обязан совпадать с провайдером и размерностью индекса; смена провайдера = полный re-ingest всей коллекции
- `text-embedding-3-small` выбран за: хорошее качество на кириллице, стоимость $0.02/M токен, 1536 dims — достаточно для правовых текстов без перерасхода
- Батчинг: 100 чанков за вызов, `MAX_CHARS=6000` (кириллица ≈ 1 char/token)

### Vector DB: Qdrant Cloud

| Критерий | Qdrant | Pinecone | Weaviate | pgvector |
|---|---|---|---|---|
| Нативный hybrid (dense+sparse) | ✅ | ✅ | ✅ | ❌ |
| Fusion (RRF из коробки) | ✅ | ❌ | ❌ | ❌ |
| Payload-фильтры по метаданным | ✅ | ✅ | ✅ | ✅ |
| Sparse IDF Modifier | ✅ | ❌ | ❌ | ❌ |
| Self-hosted + Cloud | ✅ | Cloud only | ✅ | Self only |

Qdrant выбран за нативный `FusionQuery(RRF)` и `Modifier.IDF` для sparse — единственный managed-сервис с RRF из коробки без custom-логики на стороне приложения.

### Reranker: Cohere `rerank-v3.5`

- Мультиязычная модель — поддерживает русский без дополнительной настройки
- Cross-encoder архитектура: рассматривает пару (запрос, документ) целиком, что превосходит bi-encoder cosine similarity для точного ранжирования
- **Однако ablation показал:** на golden set НП ВС РК reranker снижает faithfulness (−0.004 по сравнению с baseline, +0.042 при отключении вместе с HyDE). Это не означает, что reranker плохой — на других распределениях вопросов он может помочь; на узкоспецифичном правовом датасете он переставляет процессуально-правильные, но тематически менее точные чанки выше

### FastAPI + Next.js 14

- FastAPI: async-first, pydantic-валидация I/O, автогенерация OpenAPI, нативная интеграция с uvicorn
- Next.js 14: SSR для SEO (трудовое право — высокочастотные поисковые запросы), streaming-рендеринг ответов через Server Components

---

## 11. Структура проекта

```
enbek-ai/
├── apps/
│   └── api/                  # FastAPI-приложение
│       ├── main.py           # CORS, lifespan, маршрутизация
│       ├── graph.py          # LangGraph 9-node пайплайн
│       └── routes/ask.py     # POST /api/v1/ask
├── packages/
│   ├── config.py             # Pydantic Settings — все env-переменные
│   ├── llm.py                # OpenAI primary + Gemini fallback
│   ├── multimodal.py         # PDF/DOCX/image обработка
│   └── rag/
│       ├── embeddings.py     # text-embedding-3-small, batch 100
│       ├── qdrant_client.py  # коллекция kz_legal, hybrid RRF
│       ├── prompts.py        # системные промпты, RAG-шаблон
│       ├── ingestion/
│       │   ├── scrape_adilet.py         # кодексы, законы, ПП, приказы
│       │   ├── scrape_dialog_egov.py    # Q&A Минтруда
│       │   ├── scrape_adilet_history.py # исторические редакции
│       │   ├── scrape_tkrk.py           # tkrk.kz методология
│       │   ├── scrape_govkz_methodology.py
│       │   └── metadata.py              # enrich() + LLM topic-tagging
│       ├── retrieval/
│       │   └── reranker.py   # Cohere rerank-v3.5
│       └── advanced/
│           ├── verifier.py          # Self-RAG verifier
│           └── query_rephraser.py   # HyDE + synonyms + decompose
├── mcp/                      # Автономный MCP-сервер (Ollama + Qdrant)
│   ├── tools.py              # mask_pii, retrieve, search_labor_code
│   └── README.md             # Установка для Claude Desktop/Code/Cursor
├── apps/web/                 # Next.js 14 фронтенд
├── scripts/
│   ├── ingest.py             # полный ingest-пайплайн
│   ├── run_ragas_evals.py    # RAGAS evaluation runner
│   ├── build_cross_doc_edges.py  # LLM-построение cross-doc графа
│   ├── check_updates.py      # мониторинг обновлений adilet.zan.kz
│   └── check_urls.py         # проверка доступности URL в базе
├── data/
│   ├── golden/np_golden.jsonl     # 25 эталонных пар НП ВС РК
│   ├── evals/                     # ragas_final_*.json, ragas_ablation_*.json
│   └── chunks/annual_norms.json   # ежегодные нормы (локальный backup)
├── Dockerfile.api            # production image
├── docker-compose.yml        # локальный запуск
└── pyproject.toml            # зависимости (uv)
```

---

## 12. MCP — локальная защита ПДн

Директория `./mcp` содержит **автономный MCP-сервер** для интеграции Enbek AI в Claude Desktop, Claude Code, Cursor и Windsurf.

**Ключевая особенность:** персональные данные пользователя (ФИО, ИИН, адрес) маскируются **локально** через Ollama (`llama3.2:3b`) перед отправкой в Qdrant — ни один внешний API не видит ПДн.

Три инструмента: `mask_pii` (маскировка), `retrieve` (поиск по Qdrant), `search_labor_code` (mask + retrieve в одном вызове).

**[Полная документация по установке → `./mcp`](./mcp)**

---

## Observability

Все LLM-вызовы трассируются через **LangSmith** (проект `enbek-ai`).

### Что отслеживается

| Показатель | Инструмент | Где смотреть |
|---|---|---|
| Latency по узлам LangGraph | LangSmith traces | Timeline каждого трейса: classifier → retriever → synthesizer |
| Общая latency запроса | LangSmith | Агрегированный дашборд, P50/P95 |
| Токены по узлам (input / output) | LangSmith | Token usage per run |
| Error rate / исключения | LangSmith | Runs с `error` статусом |
| Качество retrieval (faithfulness, context_recall) | RAGAS 0.2.6 | `data/evals/ragas_final_*.json` |
| Стоимость запроса | LangSmith | Total tokens × тариф модели |

### Ключевые метрики продакшна

- **Среднее время ответа:** ~7 сек (Basic конфигурация)
- **Faithfulness:** 0.714 (Basic) — доля утверждений, подтверждённых источниками
- **Context recall:** 0.640 — полнота извлечения нужных норм
- **Стоимость запроса:** ~$0.002–0.005 (gpt-4.1-mini, multi-hop синтез)

```bash
# Переменные для включения трейсинга
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=enbek-ai
```

---

## 13. Быстрый старт

### Переменные окружения (`.env`)

```env
OPENAI_API_KEY=...
GEMINI_API_KEY=...
QDRANT_URL=...
QDRANT_API_KEY=...
COHERE_API_KEY=...
LLAMA_CLOUD_API_KEY=...
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=enbek-ai
LANGCHAIN_TRACING_V2=true
```

### Backend (FastAPI)

```bash
uv sync
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Web (Next.js)

```bash
cd apps/web
npm install
npm run dev  # http://localhost:3000
```

### Docker (production)

```bash
docker compose up api
# API доступен на http://localhost:8000
```

### Ingest (загрузка данных в Qdrant)

```bash
uv run python scripts/ingest.py
```

### RAGAS Evaluation

```bash
uv run python scripts/run_ragas_evals.py
# Результаты → data/evals/ragas_final_<timestamp>.json
```

### Обслуживание базы знаний

```bash
# Мониторинг обновлений законодательства
uv run python scripts/check_updates.py

# Проверка доступности ссылок в Qdrant
uv run python scripts/check_urls.py
```

---

## 14. Чеклист соответствия заданию

Требования курса LLM Engineer (финальный проект).

### 3.1 Архитектура и оркестрация

| Требование | Реализация | Статус |
|---|---|---|
| LangGraph с многошаговым workflow, ветвлениями, циклами | 9-node граф: classifier (3 ветки) → qa/appeal/out_of_scope; citation_guard loop ≤3; verifier retry ([§7](#7-архитектура-rag-langgraph-9-узлов), [ARCHITECTURE.md](./ARCHITECTURE.md)) | ✅ |
| Собственный MCP-сервер с 2–3 содержательных tool'а | `mcp/tools.py`: `mask_pii`, `retrieve`, `search_labor_code` — 3 tool'а; Ollama + Qdrant ([§12](#12-mcp--локальная-защита-пдн), [mcp/README.md](./mcp/README.md)) | ✅ |
| Собственный Skill с SKILL.md, триггерами и структурой | `SKILL.md` + `.claude/commands/labor-law.md`; триггеры по ТК РК, трудовым спорам; формат ответа, иерархия источников | ✅ |

### 3.2 Работа с данными

| Требование | Реализация | Статус |
|---|---|---|
| RAG-пайплайн с обоснованием chunking / embeddings / vector DB / reranker | Parent-child чанкинг; `text-embedding-3-small` 1536d; Qdrant hybrid RRF; Cohere rerank-v3.5 ([§3–§5](#3-стратегия-чанкинга-parent-child--small-to-big), [§10](#10-обоснование-инженерных-выборов)) | ✅ |
| Парсинг PDF / DOCX / HTML или скрапинг сайтов | async httpx + selectolax (adilet, egov, tkrk, gov.kz); PDF LlamaParse + PyMuPDF ([§2](#2-сбор-данных), [§8](#8-мультимодальность)) | ✅ |
| Мультимодальность (vision / OCR / audio / видео) | Vision OCR для изображений и сканированных PDF через gpt-4.1 vision; LlamaParse для структурированных PDF/DOCX ([§8](#8-мультимодальность)) | ✅ |

### 3.3 Мониторинг и оценка

| Требование | Реализация | Статус |
|---|---|---|
| Логирование и трейсинг LLM-вызовов | LangSmith (`LANGCHAIN_TRACING_V2=true`): latency по узлам, токены, цепочки трейсов, error rate — дашборд проекта `enbek-ai` ([§ Observability](#observability)) | ✅ |
| Golden dataset, автоматизированный прогон, 2+ метрики | Вручную верифицированные эталонные пары по НП ВС РК; 5 метрик RAGAS 0.2.6; `scripts/run_ragas_evals.py` ([§6](#6-golden-dataset--25-эталонных-пар), [EVALS.md](./EVALS.md)) | ✅ |
| A/B тестирование с метриками и выводами | Basic vs Advanced vs Graph (3 конфигурации) + 7 ablation-прогонов; вывод: `no_hyde_rerank` оптимум ([§9](#9-эвалуация), [EVALS.md](./EVALS.md)) | ✅ |

### 3.4 Гиперпараметры и оптимизация

| Требование | Реализация | Статус |
|---|---|---|
| Обоснование выбора LLM: стоимость / latency / качество | `gpt-4.1-mini`: баланс стоимости и кириллицы; fallback `gemini-2.5-flash`; подробная таблица сравнения ([§10](#10-обоснование-инженерных-выборов)) | ✅ |
| Температура, top_p, max_tokens с обоснованием | synthesizer: `temp=0.1` (детерминизм норм); classifier/judge: `temp=0`; HyDE: `temp=0.7` (творческий гипотетический документ); ablation показал оптимум при `temp=0.1` для синтеза | ✅ |

### Рекомендуемые требования (раздел 4)

| Требование | Реализация | Статус |
|---|---|---|
| Guardrails / PII-фильтрация | Ollama `llama3.2:3b` маскирует ПДн локально перед Qdrant; `_strip_ungrounded_urls` как output guardrail ([§12](#12-mcp--локальная-защита-пдн)) | ✅ |
| Fallback-стратегия между моделями | OpenAI → Gemini через OpenAI-compatible endpoint (`packages/llm.py`) | ✅ |
| Контейнеризация Docker | `Dockerfile.api` + `docker-compose.yml`, однокомандный локальный запуск ([§13](#13-быстрый-старт)) | ✅ |
| Деплой | Локальный запуск через Docker Compose | ✅ |
| CI/CD GitHub Actions | — | ❌ |
| Аутентификация пользователей | — | ❌ |

### Артефакты сдачи

| Артефакт | Файл | Статус |
|---|---|---|
| GitHub репозиторий с кодом | текущий репозиторий | ✅ |
| README с архитектурой и инструкцией | `README.md` (этот файл) | ✅ |
| ARCHITECTURE.md / mindmap | [ARCHITECTURE.md](./ARCHITECTURE.md) | ✅ |
| EVALS.md с golden dataset, метриками, A/B | [EVALS.md](./EVALS.md) | ✅ |
| SKILL.md с триггерами и структурой | [SKILL.md](./SKILL.md) | ✅ |
| Презентация (10–15 слайдов) | — | ⏳ |
